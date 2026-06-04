"""行业拓客模块 — API + 页面"""
import sys, json, logging, os, time, urllib.request, urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path.home() / "bdss-op"))

from flask import Blueprint, request, jsonify, render_template_string
from openpyxl import Workbook

logger = logging.getLogger(__name__)
bp = Blueprint("industry", __name__)

QCC_TOKEN = os.environ.get("QCC_TOKEN", "Bearer MOA3jDGcaXhTXZS7DHqcBSDFoGNxk4xW1KatqqOxKK2b5dkO")

# HTML template loaded from templates/industry.html


@bp.route("/industry")
def industry_page():
    from flask import make_response, send_from_directory
    resp = make_response(send_from_directory(str(Path(__file__).parent / "templates"), "industry.html"))
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@bp.route("/api/industry_search")
def api_industry_search():
    """Step 1: 企查查搜公司"""
    keyword = request.args.get("keyword", "").strip()
    companies = []
    seen_names = set()
    keywords = [kw.strip() for kw in keyword.replace("，", ",").split(",") if kw.strip()]
    if not keywords:
        return jsonify(success=False, error="请输入关键词")
    
    for kw in keywords:
        try:
            _p = {"jsonrpc": "2.0", "id": "1", "method": "tools/call",
                  "params": {"name": "get_company_by_query", "arguments": {"searchKey": kw}}}
            _h = {"Authorization": QCC_TOKEN, "Content-Type": "application/json"}
            _r = urllib.request.Request("https://agent.qcc.com/mcp/company/stream",
                data=json.dumps(_p).encode(), headers=_h, method='POST')
            _resp = urllib.request.urlopen(_r, timeout=15)
            for _line in _resp.read().decode().split('\n'):
                if _line.startswith('data: '):
                    _d = json.loads(_line[6:])
                    if 'result' in _d and 'content' in _d['result']:
                        for _c in _d['result']['content']:
                            _t = _c.get('text', '')
                            if _t:
                                for _e in json.loads(_t).get("企业信息", []):
                                    name = _e.get("企业名称", "")
                                    if name and name not in seen_names:
                                        seen_names.add(name)
                                        companies.append({"name": name, "credit_code": _e.get("统一社会信用代码", ""), "legal_person": _e.get("法定代表人名称", ""), "status": _e.get("状态", ""), "phone": ""})
        except Exception as e:
            logger.warning(f"企查查关键词失败 '{kw}': {e}")
    
    # 快捷查电话：对前3家公司查百度地图（让表格立即显示部分电话）
    from skills.lite_search import search_baidumap_poi
    for c in companies[:3]:
        try:
            pois = search_baidumap_poi(c["name"])
            for p in pois:
                if p.get("phone"):
                    c["phone"] = p["phone"]
                    break
        except Exception as _e:
            logger.debug(f"忽略: {_e}")

    # 生成搜索结果 Excel 下载链接
    out_dir = Path("/tmp/bdss_uploads")
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"search_{int(time.time())}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "企查查结果"
    ws.append(["公司名称", "统一社会信用代码", "法定代表人", "状态"])
    for c in companies:
        lp = c.get("legal_person", "")
        if isinstance(lp, list):
            lp = "、".join(str(x) for x in lp)
        ws.append([c["name"], c.get("credit_code",""), lp, c.get("status","")])
    ws.column_dimensions['A'].width = 35
    ws.column_dimensions['B'].width = 22
    wb.save(str(path))
    return jsonify(success=True, companies=companies, total=len(companies), keyword=keyword, excel_url=f"/api/download/{path.name}")

# AI 配置存储
_ai_config = {"api_key": "", "model": "gpt-4o-mini"}

@bp.route("/api/ai_config", methods=["GET", "POST"])
def api_ai_config():
    """获取/更新 AI 配置"""
    config_path = Path("/tmp/bdss_ai_config.json")
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        _ai_config.update(data)
        with open(config_path, "w") as f:
            json.dump(_ai_config, f, ensure_ascii=False)
        # 写入选中环境变量，使 AISearch 能读取到
        os.environ["BDSS_AI_API_KEY"] = _ai_config.get("api_key", "")
        os.environ["BDSS_AI_MODEL"] = _ai_config.get("model", "gpt-4o-mini")
        return jsonify(success=True)
    if config_path.exists():
        with open(config_path) as f:
            return jsonify(json.load(f))
    return jsonify(**_ai_config)

_step2_jobs: dict[str, dict] = {}
def _save_job_to_db(job_id: str, job: dict):
    """持久化 job 状态到 SQLite"""
    try:
        from bidding_monitor import get_db, close_db
        conn = get_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS step2_jobs (
                job_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO step2_jobs (job_id, data, created_at) VALUES (?, ?, ?)",
            (job_id, json.dumps({k: v for k, v in job.items() if k != 'results'}, ensure_ascii=False), time.time()),
        )
        conn.commit()
    except Exception as _e:
        logger.debug(f"忽略: {_e}")

def _load_jobs_from_db():
    """从 SQLite 恢复未完成的 job"""
    try:
        from bidding_monitor import get_db, close_db
        conn = get_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS step2_jobs (
                job_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        rows = conn.execute("SELECT job_id, data FROM step2_jobs ORDER BY created_at DESC LIMIT 10").fetchall()
        for job_id, data_json in rows:
            try:
                job = json.loads(data_json)
                if job.get("status") == "running":
                    job["status"] = "lost"  # 服务器重启后标记为丢失
                _step2_jobs[job_id] = job
            except Exception as _e:
                logger.debug(f"忽略: {_e}")
    except Exception as _e:
        logger.debug(f"忽略: {_e}")

_load_jobs_from_db()
@bp.route("/api/step2_start", methods=["POST"])
def api_step2_start():
    """启动查电话任务，返回 job_id"""
    import uuid
    body = request.get_json(silent=True) or {}
    companies = body.get("companies", [])
    job_id = uuid.uuid4().hex[:12]
    job = {
        "status": "running", "total": len(companies), "done": 0, "phones": 0,
        "log": [], "results": [], "excel_url": "", "contacts": [],
    }
    _step2_jobs[job_id] = job
    _save_job_to_db(job_id, job)

    from skills.lite_search import search_company_phones
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    def _run():
        lock = threading.Lock()
        def _search(c):
            name = c.get("name", "")
            if not name: return
            with lock:
                job["log"].append(f"[{job['done']+1}/{job['total']}] {name}")
            try:
                r = search_company_phones(name, log_detail=True)
                phones = r.get("phones", [])
                c["phone"] = " | ".join(phones)
                with lock:
                    job["phones"] += len(phones)
                    for step in r.get("steps", []):
                        job["log"].append(f"  {step}")
            except Exception as e:
                with lock:
                    job["log"].append(f"  \u9519\u8bef: {str(e)[:50]}")
            with lock:
                job["results"].append(c)
                job["done"] += 1

        with ThreadPoolExecutor(max_workers=5) as ex:
            fs = [ex.submit(_search, c) for c in companies if c.get("name")]
            for f in as_completed(fs):
                f.result()

        out_dir = Path("/tmp/bdss_uploads")
        out_dir.mkdir(exist_ok=True)
        path = out_dir / f"step2_{job_id}.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "获客结果"
        ws.append(["公司名称", "统一社会信用代码", "法定代表人", "状态", "电话"])
        for r in job["results"]:
            lp = r.get("legal_person", "")
            if isinstance(lp, list):
                lp = "、".join(str(x) for x in lp)
            ws.append([r.get("name",""), r.get("credit_code",""), lp, r.get("status",""), r.get("phone","")])
        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['E'].width = 45
        wb.save(str(path))
        job["excel_url"] = f"/api/download/{path.name}"
        job["contacts"] = [{"name": c["name"], "phone": c["phone"]} for c in job["results"] if c.get("phone")]
        job["status"] = "done"

    import threading as _t
    _t.Thread(target=_run, daemon=True).start()
    return jsonify(success=True, job_id=job_id, total=len(companies))


@bp.route("/api/step2_progress/<job_id>")
def api_step2_progress(job_id):
    job = _step2_jobs.get(job_id)
    if not job:
        return jsonify(status="not_found")
    return jsonify({
        "status": job["status"], "total": job["total"], "done": job["done"],
        "phones": job["phones"], "log": job["log"][-50:],
        "excel_url": job.get("excel_url", ""), "contacts": job.get("contacts", []),
        "results": job.get("results", []),
    })


@bp.route("/api/download/<filename>")
def api_download(filename):
    from flask import send_file
    path = Path("/tmp/bdss_uploads") / filename
    if path.exists():
        return send_file(str(path), as_attachment=True, download_name=filename.replace("search_", "企查查名单_").replace("step2_", "获客结果_"))
    return "文件不存在", 404
def api_download(filename):
    from flask import send_file
    path = Path("/tmp/bdss_uploads") / filename
    if path.exists():
        return send_file(str(path), as_attachment=True, download_name=filename.replace("step2_", "获客结果_"))
    return "文件不存在", 404
