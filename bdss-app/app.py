#!/usr/bin/env python3
"""BDSS 批量获客系统 — 轻量版（无需 Playwright）"""
import sys, os, json, time, threading, uuid, logging
logger = logging.getLogger(__name__)
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/bdss-op"))

from flask import Flask, request, jsonify, render_template_string, send_file
from openpyxl import load_workbook, Workbook
from datetime import datetime
from skills.lite_search import search_company_phones
from bidding_monitor import scan_with_notify, get_stats, update_status
from industry_api import bp as industry_bp

app = Flask(__name__)
app.register_blueprint(industry_bp)
UPLOAD_DIR = Path("/tmp/bdss_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
tasks = {}
@app.route("/")
def index():
    tmpl = (Path(__file__).parent / "templates/index.html").read_text(encoding="utf-8")
    return render_template_string(tmpl)

@app.route("/api/dashboard")
def api_dashboard():
    """仪表盘数据"""
    from bidding_monitor import get_db, close_db
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM bidding_items").fetchone()[0]
    new_today = conn.execute("SELECT COUNT(*) FROM bidding_items WHERE matched_at > ?", (time.time() - 86400,)).fetchone()[0]
    with_phone = conn.execute("SELECT COUNT(*) FROM bidding_items WHERE phone != ''").fetchone()[0]
    contacted = conn.execute("SELECT COUNT(*) FROM bidding_items WHERE status='contacted'").fetchone()[0]
    close_db()
    return jsonify({"total": total, "new_today": new_today, "with_phone": with_phone, "contacted": contacted})


# ============ 关键词管理 API ============

@app.route("/api/keywords", methods=["GET", "POST"])
def api_keywords():
    from bidding_monitor import CCGP_KEYWORDS, OKCIS_KEYWORDS, WATER_CHEM_KEYWORDS
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        new_kw = data.get("keywords", [])
        # 持久化到文件
        kw_path = Path.home() / "bdss-op/water_chem_keywords.json"
        with open(kw_path, "w") as f:
            json.dump(new_kw, f, ensure_ascii=False)
        return jsonify(success=True, keywords=new_kw)
    # GET: 返回当前关键词
    return jsonify({
        "ccgp": CCGP_KEYWORDS,
        "okcis": OKCIS_KEYWORDS,
        "all": WATER_CHEM_KEYWORDS,
    })


# ============ 公司详情 API ============

@app.route("/api/company/<path:name>")
def api_company(name):
    from bidding_monitor import get_db, close_db
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, source, buyer, contact, phone, email, matched_at, status FROM bidding_items WHERE buyer LIKE ? ORDER BY matched_at DESC LIMIT 20",
        (f"%{name}%",),
    ).fetchall()
    return jsonify([{"id": r[0], "title": r[1], "source": r[2], "buyer": r[3],
                     "contact": r[4], "phone": r[5], "email": r[6],
                     "time": r[7], "status": r[8]} for r in rows])

# ============ 外呼系统 API ============

@app.route("/api/outcall/config", methods=["GET", "POST"])
def api_outcall_config():
    """配置阿里云外呼接口"""
    config_path = Path(__file__).parent / "outcall_config.json"
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        with open(config_path, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        return jsonify(success=True)
    if config_path.exists():
        with open(config_path) as f:
            return jsonify(json.load(f))
    return jsonify({"enabled": False, "api_url": "", "api_key": ""})

@app.route("/api/outcall/push", methods=["POST"])
def api_outcall_push():
    """推送客户名单到阿里云外呼"""
    body = request.get_json(silent=True) or {}
    contacts = body.get("contacts", [])
    if not contacts:
        return jsonify(success=False, error="没有要推送的联系人")
    config_path = Path(__file__).parent / "outcall_config.json"
    config = {"enabled": False, "api_url": "", "api_key": ""}
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    if not config.get("enabled") or not config.get("api_url"):
        return jsonify(success=False, error="未配置外呼系统，请先在设置中配置")
    # 构造请求
    payload = {
        "contacts": [{"name": c.get("name",""), "phone": c.get("phone","")} for c in contacts if c.get("phone")],
        "total": len(contacts),
    }
    import urllib.request as _req
    try:
        data = json.dumps(payload, ensure_ascii=False).encode()
        req = _req.Request(config["api_url"], data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.get('api_key','')}"})
        resp = _req.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        return jsonify(success=True, result=result, pushed=len(payload["contacts"]))
    except Exception as e:
        return jsonify(success=False, error=f"推送失败: {str(e)[:100]}")

@app.route("/api/outcall/push_bidding", methods=["POST"])
def api_outcall_push_bidding():
    """推送招标线索到外呼"""
    from bidding_monitor import get_stats
    stats = get_stats()
    contacts = []
    for item in stats["recent"]:
        if item.get("phone") and item.get("status") == "new":
            contacts.append({"name": item.get("buyer","") or item.get("title","")[:20], "phone": item["phone"]})
    if not contacts:
        return jsonify(success=False, error="没有未联系且有电话的线索")
    # 构造请求体
    from flask import request as _req_ctx
    with app.test_request_context(json={"contacts": contacts}):
        return api_outcall_push()
    pois = [p for p in pois if not p["name"].endswith(("市","省","区","县"))]
    if not pois:
        alt_keywords = [f"{keyword}公司", f"{keyword}厂", f"{keyword}企业"]
        import os as _os
        ak = _os.environ.get("BAIDU_MAP_AK", "")
        if not ak:
            try:
                from utils.env import get_ak as _get_ak
                ak = _get_ak()
            except:
                pass
        if ak:
            import urllib.request, json as _json, urllib.parse
            for alt_kw in alt_keywords:
                url = f"https://api.map.baidu.com/place/v2/search?query={urllib.parse.quote(alt_kw)}&region={urllib.parse.quote(region)}&output=json&ak={ak}&page_size=5"
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    resp = urllib.request.urlopen(req, timeout=8)
                    data = _json.loads(resp.read())
                    for poi in data.get("results", []):
                        name = poi.get("name", "")
                        if not name or name.endswith(("市","省","区","县")):
                            continue
                        if not any(p["name"] == name for p in pois):
                            pois.append({"name": name, "address": poi.get("address",""), "phone": poi.get("telephone","") or poi.get("phone",""), "uid": poi.get("uid","")})
                except:
                    pass
    return jsonify(success=True, companies=pois[:30], keyword=keyword, region=region)

@app.route("/monitor")
def monitor_page():
    tmpl = (Path(__file__).parent / "templates/monitor.html").read_text(encoding="utf-8")
    return render_template_string(tmpl)
@app.route("/api/monitor/stats")
def monitor_stats():
    return jsonify(get_stats())
@app.route("/api/monitor/scan", methods=["POST"])
def monitor_scan():
    result = scan_with_notify()
    return jsonify(result)

@app.route("/api/monitor/status", methods=["POST"])
def monitor_update_status():
    body = request.get_json(silent=True) or {}
    item_id = body.get("id")
    status = body.get("status", "new")
    notes = body.get("notes", "")
    if item_id:
        update_status(item_id, status, notes)
    return jsonify(success=True)


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify(success=False, error="请选择文件")
    ext = Path(file.filename).suffix.lower()
    if ext not in (".xlsx", ".xls"):
        return jsonify(success=False, error="仅支持 .xlsx / .xls")
    tid = uuid.uuid4().hex[:8]
    path = UPLOAD_DIR / f"{tid}{ext}"
    file.save(str(path))
    try:
        wb = load_workbook(str(path), read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if len(rows) < 2:
            return jsonify(success=False, error="文件为空")
        header = [str(c or "").strip() for c in rows[0]]
        name_col = None
        for i, h in enumerate(header):
            if "公司" in h or "企业" in h or "名称" in h or "name" in h.lower():
                name_col = i; break
        if name_col is None:
            return jsonify(success=False, error="未找到「公司名称」列")
        companies = []
        for row in rows[1:]:
            name = str(row[name_col] or "").strip()
            if name and len(name) > 1:
                companies.append({"name": name, "row": [str(c or "") for c in row], "header": header})
        if not companies:
            return jsonify(success=False, error="未找到有效公司数据")
        tasks[tid] = {"companies": companies, "results": [], "done": 0, "total": len(companies), "phones": 0, "failed": 0, "logs": [], "running": False}
        preview = [c["row"] for c in companies[:5]]
        return jsonify(success=True, task_id=tid, count=len(companies), columns=header, rows=preview)
    except Exception as e:
        return jsonify(success=False, error=f"解析失败: {str(e)}")

@app.route("/start/<tid>", methods=["POST"])
def start_search(tid):
    t = tasks.get(tid)
    if not t:
        return jsonify(success=False)
    t["running"] = True
    t["results"] = []
    t["done"] = 0
    t["phones"] = 0
    t["failed"] = 0
    t["logs"] = []
    def _run():
        for i, c in enumerate(t["companies"]):
            name = c["name"]
            t["logs"].append({"i": f"i{i}", "t": "info", "m": f"[{i+1}/{t['total']}] {name}"})
            try:
                result = search_company_phones(name)
                phones = result.get("phones", [])
                t["results"].append({"company": name, "phones": phones, "row": c["row"]})
                if phones:
                    t["phones"] += len(phones)
                    t["logs"].append({"i": f"p{i}", "t": "found", "m": f"  ✓ {len(phones)} 个: {' | '.join(phones[:3])}"})
                else:
                    t["failed"] += 1
                    t["logs"].append({"i": f"e{i}", "t": "empty", "m": f"  ✗ 未找到电话"})
            except Exception as e:
                t["failed"] += 1
                t["results"].append({"company": name, "phones": [], "row": c["row"]})
                t["logs"].append({"i": f"x{i}", "t": "empty", "m": f"  ✗ 错误: {str(e)[:50]}"})
            t["done"] += 1
            _save_result(t, tid)
        t["running"] = False
    threading.Thread(target=_run, daemon=True).start()
    return jsonify(success=True)

@app.route("/progress/<tid>")
def progress(tid):
    t = tasks.get(tid)
    if not t:
        return jsonify(done=0, total=0, percent=0, phones=0, failed=0, logs=[])
    percent = (t["done"] / t["total"] * 100) if t["total"] > 0 else 0
    return jsonify(done=t["done"], total=t["total"], percent=round(percent,1), phones=t["phones"], failed=t["failed"], logs=t["logs"][-50:])

@app.route("/download/<tid>")
def download(tid):
    path = UPLOAD_DIR / f"{tid}_result.xlsx"
    if path.exists():
        return send_file(str(path), as_attachment=True, download_name="获客结果.xlsx")
    return "文件未就绪", 404

def _save_result(t, tid):
    wb = Workbook()
    ws = wb.active
    ws.title = "获客结果"
    header = t["companies"][0]["header"] if t["companies"] else []
    ws.append(header + ["搜到电话", "电话数量"])
    for r in t["results"]:
        ws.append(r["row"] + [" | ".join(r["phones"]), len(r["phones"])])
    phone_col = len(header) + 1
    if phone_col:
        ws.cell(row=1, column=phone_col).value = "搜到电话"
        ws.column_dimensions[chr(64 + phone_col) if phone_col <= 26 else "A"].width = 40
    wb.save(str(UPLOAD_DIR / f"{tid}_result.xlsx"))


# ============ 招标导出 ============

@app.route("/api/monitor/export")
def monitor_export():
    """导出招标线索为 Excel"""
    stats = get_stats()
    wb = Workbook()
    ws = wb.active
    ws.title = "招标线索"
    ws.append(["标题", "采购单位", "联系人", "电话", "邮箱", "来源", "时间", "状态"])
    for item in stats["recent"]:
        ws.append([
            item.get("title", ""),
            item.get("buyer", ""),
            item.get("contact", ""),
            item.get("phone", ""),
            item.get("email", ""),
            item.get("source", ""),
            datetime.fromtimestamp(item.get("time", 0)).strftime("%Y-%m-%d %H:%M"),
            item.get("status", ""),
        ])
    ws.column_dimensions['A'].width = 50
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['D'].width = 25
    out = UPLOAD_DIR / "招标线索.xlsx"
    wb.save(str(out))
    return send_file(str(out), as_attachment=True, download_name="招标线索.xlsx")


# ============ 定时扫描 ============

import threading as _th
import time as _time

_SCAN_INTERVAL = 3600  # 1 小时
_last_scan_time = [0.0]

def _scheduler():
    """后台定时扫描招标"""
    _last_scan_time[0] = _time.time()
    while True:
        try:
            if _time.time() - _last_scan_time[0] >= _SCAN_INTERVAL:
                logger.info("[定时扫描] 开始...")
                from bidding_monitor import scan_with_notify, close_db
                r = scan_with_notify()
                close_db()
                logger.info(f"[定时扫描] 完成: {r['total_found']} 条, 新增 {r['new_saved']}")
                _last_scan_time[0] = _time.time()
        except Exception as e:
            logger.error(f"[定时扫描] 失败: {e}")
        _time.sleep(300)  # 每 5 分钟检查一次

# 启动后台线程
_th.Thread(target=_scheduler, daemon=True).start()
if __name__ == "__main__":
    print(f"BDSS 获客系统 http://127.0.0.1:5300")
    logger.info("定时扫描已启动 (间隔: 1 小时)")
    app.run(host="127.0.0.1", port=5300, debug=False)
    print(f"BDSS 获客系统 http://127.0.0.1:5300")
    app.run(host="127.0.0.1", port=5300, debug=False)
