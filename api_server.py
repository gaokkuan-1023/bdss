"""
BDSS HTTP API 服务

提供 RESTful 接口，包装 main.py 的搜索功能为 HTTP API。
支持单公司和批量搜索，自动异步处理。

启动:
    python api_server.py              # 开发模式 (默认 :5000)
    python api_server.py --port 8080  # 自定义端口
    python api_server.py --verbose    # DEBUG 日志

Docker:
    docker build -t bdss-api .
    docker run -p 5000:5000 bdss-api python api_server.py

请求示例:
    curl -X POST http://localhost:5000/api/search \\
         -H "Content-Type: application/json" \\
         -d '{"company": "深圳腾讯", "engine": "all", "delay": 1500}'
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))

try:
    from flask import Flask, request, jsonify
except ImportError:
    print("[X] 需要 Flask: pip install flask")
    sys.exit(1)

from utils.helpers import setup_logger, load_companies_from_file
from main import search_company, search_all_engines

logger = logging.getLogger(__name__)

app = Flask(__name__)

# 全局配置
CONFIG = {
    "headless": True,
    "proxy": None,
    "verbose": False,
}


def _build_response(success: bool, data=None, error: str = None, status: int = 200):
    """统一响应格式"""
    resp = {"success": success}
    if data is not None:
        resp["data"] = data
    if error:
        resp["error"] = error
    return jsonify(resp), status


# ============ API 路由 ============


@app.route("/api/health", methods=["GET"])
def health():
    """健康检查"""
    return _build_response(True, {
        "status": "ok",
        "version": "1.0.0",
        "timestamp": time.time(),
    })


@app.route("/api/search", methods=["POST"])
def api_search():
    """
    搜索公司电话

    请求体 (JSON):
        company (str)      : 公司名称 (必填)
        engine (str)       : 搜索引擎, 可选 baidu/bing/sogou/google/all (默认: all)
        max_results (int)  : 每引擎打开前 N 个结果 (默认: 5)
        delay (int)        : 请求间隔毫秒 (默认: 0)
        output (str)       : 输出文件路径 (可选)

    响应:
        success (bool)
        data (dict)        : { company, phones, phone_count, engine, sources, geo_check }
        error (str)        : 错误信息
    """
    body = request.get_json(silent=True)
    if not body:
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
                company_name=company,
                max_results=max_results,
                headless=CONFIG["headless"],
                proxy=CONFIG["proxy"],
                verbose=CONFIG["verbose"],
                delay=delay,
            )
        else:
            result = search_company(
                company_name=company,
                engine=engine,
                max_results=max_results,
                headless=CONFIG["headless"],
                proxy=CONFIG["proxy"],
                verbose=CONFIG["verbose"],
                delay=delay,
            )

        # 清理输出：移除 page_text 等大数据字段
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
        import traceback
        traceback.print_exc()
        return _build_response(False, error=str(e), status=500)


@app.route("/api/search/batch", methods=["POST"])
def api_search_batch():
    """
    批量搜索

    请求体 (JSON):
        companies (list)   : 公司名称列表 (必填)
        engine (str)       : 搜索引擎 (默认: all)
        max_results (int)  : (默认: 3)
        delay (int)        : 请求间隔毫秒 (默认: 1000)
        concurrency (int)  : 并发数 (暂为 1，顺序执行)
    """
    body = request.get_json(silent=True)
    if not body:
        return _build_response(False, error="请求体必须是 JSON", status=400)

    companies = body.get("companies", [])
    if not companies or not isinstance(companies, list):
        return _build_response(False, error="companies 必须是非空列表", status=400)

    engine = body.get("engine", "all")
    max_results = body.get("max_results", 3)
    delay = body.get("delay", 1000)

    logger.info(f"[API] 批量搜索: {len(companies)} 个公司 (引擎: {engine})")

    results = []
    for i, company in enumerate(companies):
        if isinstance(company, dict):
            company = company.get("company", "")
        company = str(company).strip()
        if not company:
            continue

        logger.info(f"[API] 批量 [{i + 1}/{len(companies)}]: {company}")
        try:
            if engine == "all":
                r = search_all_engines(company, max_results=max_results,
                                       headless=CONFIG["headless"],
                                       proxy=CONFIG["proxy"],
                                       verbose=CONFIG["verbose"],
                                       delay=delay)
            else:
                r = search_company(company, engine=engine, max_results=max_results,
                                   headless=CONFIG["headless"],
                                   proxy=CONFIG["proxy"],
                                   verbose=CONFIG["verbose"],
                                   delay=delay)
            results.append({
                "company": company,
                "phones": r.get("phones", []),
                "phone_count": r.get("phone_count", 0),
            })
        except Exception as e:
            logger.error(f"[API] 批量搜索失败 {company}: {e}")
            results.append({"company": company, "phones": [], "error": str(e)})

        if delay and i < len(companies) - 1:
            time.sleep(delay / 1000)

    return _build_response(True, {
        "total": len(results),
        "engine": engine,
        "results": results,
    })


# ============ 启动 ============


def main():
    parser = argparse.ArgumentParser(description="BDSS HTTP API 服务")
    parser.add_argument("--port", "-p", type=int, default=5000, help="监听端口 (默认: 5000)")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--verbose", "-v", action="store_true", help="DEBUG 级别日志")
    parser.add_argument("--visible", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--proxy", help="代理地址")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    setup_logger(level=level)
    logger.setLevel(level)

    CONFIG["headless"] = not args.visible
    CONFIG["proxy"] = args.proxy
    CONFIG["verbose"] = args.verbose

    logger.info(f"{'=' * 50}")
    logger.info(f"BDSS API 服务启动")
    logger.info(f"  地址: http://{args.host}:{args.port}")
    logger.info(f"  接口: POST /api/search")
    logger.info(f"       POST /api/search/batch")
    logger.info(f"       GET  /api/health")
    logger.info(f"{'=' * 50}")

    app.run(host=args.host, port=args.port, debug=args.verbose)


if __name__ == "__main__":
    main()
