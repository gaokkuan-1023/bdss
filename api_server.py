"""
BDSS HTTP API 服务 + Web 界面

提供 RESTful API 和一个简单的 Web 查询页面。
支持可选的 API Token 认证。

启动:
    python api_server.py                    # 开发模式 (默认 :5000)
    python api_server.py --port 8080        # 自定义端口
    python api_server.py --verbose          # DEBUG 日志
    python api_server.py --token mysecret   # 开启 Token 认证
"""

import argparse
import hmac
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from flask import Flask, request, jsonify, render_template_string, abort
except ImportError:
    print("[X] 需要 Flask: pip install flask")
    sys.exit(1)

from utils.helpers import setup_logger
from main import search_company, search_all_engines

logger = logging.getLogger(__name__)

app = Flask(__name__)

# 全局配置
CONFIG = {
    "headless": True,
    "proxy": None,
    "verbose": False,
    "token": None,
}

# ============ HTML 模板（内嵌，免建 templates 目录）============
INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BDSS - 公司电话查询</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
  .container{max-width:720px;margin:0 auto;padding:40px 20px}
  h1{font-size:2rem;font-weight:800;text-align:center;margin-bottom:8px;background:linear-gradient(135deg,#38bdf8,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
  .subtitle{text-align:center;color:#94a3b8;margin-bottom:32px;font-size:.95rem}
  .card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px;margin-bottom:16px}
  label{display:block;margin-bottom:6px;font-weight:600;font-size:.9rem;color:#94a3b8}
  .row{display:flex;gap:12px;flex-wrap:wrap}
  .row>*{flex:1;min-width:120px}
  input,select{width:100%;padding:10px 12px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:.95rem;outline:none}
  input:focus,select:focus{border-color:#38bdf8}
  button{width:100%;padding:12px;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:1rem;font-weight:600;cursor:pointer;margin-top:16px}
  button:hover{background:#1d4ed8}
  button:disabled{opacity:.5;cursor:not-allowed}
  #status{text-align:center;padding:12px;color:#94a3b8;display:none}
  #result{display:none}
  .phone-list{list-style:none}
  .phone-item{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:#0f172a;border-radius:8px;margin-bottom:8px;font-family:monospace;font-size:1.1rem;letter-spacing:1px}
  .phone-item .tag{font-size:.7rem;padding:2px 8px;border-radius:4px;font-weight:600}
  .tag-mobile{background:rgba(34,197,94,.15);color:#22c55e}
  .tag-landline{background:rgba(234,179,8,.15);color:#eab308}
  .tag-service{background:rgba(168,85,247,.15);color:#a855f7}
  .summary{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}
  .stat{text-align:center;padding:12px;background:#0f172a;border-radius:8px}
  .stat .num{font-size:1.5rem;font-weight:700;color:#38bdf8}
  .stat .label{font-size:.75rem;color:#64748b;margin-top:2px}
  .error-box{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:8px;padding:12px;color:#fca5a5;margin-top:12px;display:none}
  .meta{font-size:.8rem;color:#64748b;margin-top:8px}
</style>
</head>
<body><div class="container">
  <h1>🔍 BDSS</h1>
  <p class="subtitle">公司联系电话查询 · 多引擎搜索</p>
  <div class="card">
    <form id="f">
      <label>公司名称</label>
      <input type="text" id="company" placeholder="例如：深圳腾讯计算机系统有限公司" required>
      <div class="row" style="margin-top:12px">
        <div><label>引擎</label><select id="engine"><option value="all">全部引擎</option><option value="baidu">百度</option><option value="bing">必应</option><option value="sogou">搜狗</option></select></div>
        <div><label>延迟(ms)</label><input type="number" id="delay" value="1500" min="0" step="100"></div>
      </div>
      <button type="submit" id="btn">🔍 查询电话</button>
    </form>
  </div>
  <div id="status">⏳ 搜索中...</div>
  <div class="error-box" id="err"></div>
  <div id="result">
    <div class="card">
      <h3 id="cn" style="margin-bottom:12px"></h3>
      <div class="summary">
        <div class="stat"><div class="num" id="pc">0</div><div class="label">电话数</div></div>
        <div class="stat"><div class="num" id="ec">0</div><div class="label">引擎数</div></div>
        <div class="stat"><div class="num" id="gc">0</div><div class="label">城市</div></div>
      </div>
      <ul class="phone-list" id="pl"></ul>
    </div>
    <div class="card"><label>来源</label><div style="max-height:200px;overflow-y:auto;font-size:.8rem;color:#94a3b8" id="sl"></div></div>
  </div>
</div>
<script>
  document.getElementById('f').addEventListener('submit', async e => {
    e.preventDefault();
    const c = document.getElementById('company').value.trim();
    if(!c) return;
    const btn=document.getElementById('btn'), st=document.getElementById('status'), r=document.getElementById('result'), er=document.getElementById('err');
    btn.disabled=true; btn.textContent='⏳ 搜索中...'; st.style.display='block'; r.style.display='none'; er.style.display='none';
    try {
      const resp = await fetch('/api/search', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({company:c, engine:document.getElementById('engine').value, delay:parseInt(document.getElementById('delay').value)||0, max_results:5}) });
      const d = await resp.json();
      if(!d.success) { er.textContent=d.error||'失败'; er.style.display='block'; return; }
      const data = d.data;
      document.getElementById('cn').textContent = data.company||c;
      document.getElementById('pc').textContent = data.phone_count||0;
      document.getElementById('ec').textContent = data.engine||'—';
      const cities = (data.geo_check && data.geo_check.cities)||[];
      document.getElementById('gc').textContent = cities.length;
      const pl = document.getElementById('pl'); pl.innerHTML='';
      if(data.phones&&data.phones.length) {
        data.phones.forEach(p => {
          const t = p.startsWith('0')?'landline':p.startsWith('4')||p.startsWith('8')?'service':'mobile';
          const l = {mobile:'手机',landline:'固话',service:'热线'}[t]||'';
          pl.innerHTML += '<li class=phone-item><span>'+p+'</span><span class="tag tag-'+t+'">'+l+'</span></li>';
        });
      } else pl.innerHTML = '<li style="color:#94a3b8;text-align:center;padding:20px">未找到电话</li>';
      const sl=document.getElementById('sl'); sl.innerHTML='';
      if(data.sources) data.sources.slice(0,20).forEach(s => { sl.innerHTML += '<div style=margin-bottom:4px><span style=color:#38bdf8;font-family:monospace>'+s.phone+'</span> → '+(s.title||'')+'</div>'; });
      if(data.sources&&data.sources.length>20) sl.innerHTML += '<div style=color:#64748b>...还有'+(data.sources.length-20)+'条</div>';
      r.style.display='block';
    } catch(e) { er.textContent='网络错误: '+e.message; er.style.display='block'; }
    finally { btn.disabled=false; btn.textContent='🔍 查询电话'; st.style.display='none'; }
  });
</script></body></html>"""


def _check_auth():
    """检查请求是否携带有效的 API Token（已配置时）"""
    token = CONFIG.get("token")
    if not token:
        return  # 未配置 Token，放行
    auth_header = request.headers.get("Authorization", "")
    # 支持 "Bearer xxx" 和直接 "xxx" 两种格式
    provided = auth_header.replace("Bearer ", "").strip()
    if not hmac.compare_digest(provided, token):
        abort(401, description="无效的 API Token，请在 Header 中传递 Authorization: Bearer <token>")


def _build_response(success: bool, data=None, error: str = None, status: int = 200):
    resp = {"success": success}
    if data is not None:
        resp["data"] = data
    if error:
        resp["error"] = error
    return jsonify(resp), status


@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML)


@app.route("/api/health", methods=["GET"])
def health():
    return _build_response(True, {
        "status": "ok",
        "version": "1.0.0",
        "timestamp": time.time(),
    })


@app.route("/api/search", methods=["POST"])
def api_search():
    _check_auth()
    body = request.get_json(silent=True)
    if body is None:
        return _build_response(False, error="请求体必须是 JSON", status=400)

    company = body.get("company", "").strip()
    if not company:
        return _build_response(False, error="company 不能为空", status=400)

    engine = body.get("engine", "all")
    max_results = body.get("max_results", 5)
    delay = body.get("delay", 0)

    logger.info(f"[API] 搜索: {company} (引擎: {engine}, max={max_results}, delay={delay})")
    try:
        if engine == "all":
            result = search_all_engines(
                company_name=company, max_results=max_results,
                headless=CONFIG["headless"], proxy=CONFIG["proxy"],
                verbose=CONFIG["verbose"], delay=delay,
            )
        else:
            result = search_company(
                company_name=company, engine=engine, max_results=max_results,
                headless=CONFIG["headless"], proxy=CONFIG["proxy"],
                verbose=CONFIG["verbose"], delay=delay,
            )

        clean = {
            "company": result.get("company"),
            "phones": result.get("phones", []),
            "phone_count": result.get("phone_count", 0),
            "engine": result.get("engine", engine),
            "sources": [
                {"phone": s["phone"], "url": s.get("url", ""), "title": s.get("title", "")}
                for s in result.get("sources", [])
            ],
            "geo_check": result.get("geo_check"),
        }
        return _build_response(True, clean)
    except Exception as e:
        logger.error(f"[API] 搜索失败: {e}")
        import traceback; traceback.print_exc()
        return _build_response(False, error=str(e), status=500)


@app.route("/api/search/batch", methods=["POST"])
def api_search_batch():
    _check_auth()
    body = request.get_json(silent=True)
    if body is None:
        return _build_response(False, error="请求体必须是 JSON", status=400)
    companies = body.get("companies", [])
    if not companies or not isinstance(companies, list):
        return _build_response(False, error="companies 必须是非空列表", status=400)

    engine = body.get("engine", "all")
    max_results = body.get("max_results", 3)
    delay = body.get("delay", 1000)
    logger.info(f"[API] 批量搜索: {len(companies)} 个公司")

    results = []
    for i, c in enumerate(companies):
        company = str(c.get("company", c)).strip() if isinstance(c, dict) else str(c).strip()
        if not company:
            continue
        logger.info(f"[API] 批量 [{i+1}/{len(companies)}]: {company}")
        try:
            if engine == "all":
                r = search_all_engines(company, max_results=max_results,
                                       headless=CONFIG["headless"], proxy=CONFIG["proxy"],
                                       verbose=CONFIG["verbose"], delay=delay)
            else:
                r = search_company(company, engine=engine, max_results=max_results,
                                   headless=CONFIG["headless"], proxy=CONFIG["proxy"],
                                   verbose=CONFIG["verbose"], delay=delay)
            results.append({"company": company, "phones": r.get("phones", []), "phone_count": r.get("phone_count", 0)})
        except Exception as e:
            logger.error(f"[API] 批量搜索失败 {company}: {e}")
            results.append({"company": company, "phones": [], "error": str(e)})
        if delay and i < len(companies) - 1:
            time.sleep(delay / 1000)
    return _build_response(True, {"total": len(results), "engine": engine, "results": results})


def main():
    parser = argparse.ArgumentParser(description="BDSS HTTP API 服务")
    parser.add_argument("--port", "-p", type=int, default=5000, help="监听端口 (默认: 5000)")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认: 127.0.0.1)")
    parser.add_argument("--verbose", "-v", action="store_true", help="DEBUG 级别日志")
    parser.add_argument("--debug", action="store_true", help="启用 Flask 调试模式（仅限开发环境）")
    parser.add_argument("--visible", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--proxy", help="代理地址")
    parser.add_argument("--token", help="API Token（设置后需在请求 Header 传递）")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    setup_logger(level=level)
    logger.setLevel(level)

    CONFIG["headless"] = not args.visible
    CONFIG["proxy"] = args.proxy
    CONFIG["verbose"] = args.verbose
    CONFIG["token"] = args.token or os.environ.get("BDSS_API_TOKEN")

    logger.info(f"{'='*50}")
    logger.info(f"BDSS API 服务启动")
    logger.info(f"  🌐 Web界面: http://{args.host}:{args.port}")
    logger.info(f"  📡 API:  POST /api/search")
    logger.info(f"  📡 API:  POST /api/search/batch")
    logger.info(f"  📡 API:  GET  /api/health")
    if CONFIG["token"]:
        logger.info(f"  🔐 Token 认证已开启")
    logger.info(f"{'='*50}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
