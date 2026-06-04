"""轻量搜索模块 — 不走浏览器，直接 HTTP 请求"""
import json
import logging
import os
import re
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def search_bing(query: str, max_results: int = 5) -> list[dict]:
    """通过 HTTP 请求搜必应（不需要浏览器）"""
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={max_results}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Bing 搜索失败: {e}")
        return []

    results = []
    # 提取搜索结果：<li class="b_algo"> 中的 h2 > a
    for m in re.finditer(r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>.*?<h2>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        url = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if title and url and len(results) < max_results:
            results.append({"title": title, "url": url, "snippet": "", "index": len(results) + 1})
    return results


def search_baidu(query: str, max_results: int = 5) -> list[dict]:
    """通过 HTTP 请求搜百度"""
    url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}&ie=utf-8"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"百度搜索失败: {e}")
        return []

    results = []
    # 百度PC版搜索结果在 h3 > a 中
    for m in re.finditer(r'<h3[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        url = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if title and not url.startswith("http"):
            # 百度结果链接需要处理
            if "baidu.com/link" in url:
                # 提取真实 URL
                url_param = re.search(r"url=([^&]+)", url)
                if url_param:
                    try:
                        url = urllib.parse.unquote(url_param.group(1))
                    except Exception as _ex:
                        logger.debug(f"忽略: {_ex}")
        if title and url and len(results) < max_results:
            results.append({"title": title, "url": url, "snippet": "", "index": len(results) + 1})

    return results


def fetch_page_text(url: str, timeout: int = 15) -> str:
    """获取页面纯文本"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        html = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:10000]
    except Exception:
        return ""


def search_and_open(query: str, engine: str = "baidu", max_results: int = 3) -> tuple[list, str]:
    """搜索并打开结果页面，返回 (opened_pages, search_page_text)"""
    if engine == "bing":
        results = search_bing(query, max_results)
    else:
        results = search_baidu(query, max_results)

    opened = []
    search_text = ""

    for r in results:
        page_text = fetch_page_text(r["url"])
        opened.append({**r, "page_text": page_text})
        if not search_text:
            search_text = page_text[:5000]

    return opened, search_text


PHONE_EXTRACTOR = None

def extract_phones_from_text(text: str) -> list[str]:
    """从文本中提取中国电话号码（委托 PhoneExtractor）"""
    global PHONE_EXTRACTOR
    if PHONE_EXTRACTOR is None:
        from extractors.phone import PhoneExtractor
        PHONE_EXTRACTOR = PhoneExtractor(prefer_nearby=False)
    return PHONE_EXTRACTOR.extract(text)


SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def search_bidding(keyword: str, max_pages: int = 1) -> dict:
    """从招标采购导航网搜招标公告，提取电话"""
    all_phones = set()
    items = []
    for page in range(1, max_pages + 1):
        url = f"https://www.okcis.cn/search?q={urllib.parse.quote(keyword)}&page={page}"
        try:
            req = urllib.request.Request(url, headers=SEARCH_HEADERS)
            resp = urllib.request.urlopen(req, timeout=10)
            html = resp.read().decode("utf-8", errors="replace")
            for m in re.finditer(r"1[3-9]\d{9}", html):
                all_phones.add(m.group())
            for m in re.finditer(r'<div class="tit">\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
                items.append({"title": m.group(2).strip(), "url": m.group(1)})
        except Exception as _ex:
            logger.debug(f"忽略: {_ex}")
    return {"phones": sorted(all_phones), "phone_count": len(all_phones), "items": items[:10], "source": "招标采购导航网"}


def search_baidumap_poi(company: str) -> list[dict]:
    from utils.env import get_ak
    """通过百度地图 Place API 搜索公司 POI 及电话"""
    ak = os.environ.get("BAIDU_MAP_AK", "")
    if not ak:
        # 尝试读 .env 文件
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("BAIDU_MAP_AK="):
                    ak = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not ak:
        logger.warning("未配置 BAIDU_MAP_AK，跳过百度地图查询")
        return []

    query = urllib.parse.quote(company)
    region = urllib.parse.quote("全国")
    url = f"https://api.map.baidu.com/place/v2/search?query={query}&region={region}&output=json&ak={ak}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        results = []
        for poi in data.get("results", []):
            phone = poi.get("telephone", "") or poi.get("phone", "")
            results.append({
                "name": poi.get("name", ""),
                "address": poi.get("address", ""),
                "phone": phone,
                "uid": poi.get("uid", ""),
            })
        return results
    except Exception as e:
        logger.warning(f"百度地图 API 查询失败: {e}")
        return []


def search_company_phones(company: str, log_detail: bool = False) -> dict:
    """一站式搜索公司电话：百度地图 POI + 顺企网，返回电话和步骤日志"""
    all_phones = set()
    sources = []
    steps = [] if log_detail else None

    def _log(msg):
        if steps is not None:
            steps.append(msg)

    # 1. 百度地图 POI（最准）
    _log(f"1/3 百度地图POI查询: {company}")
    pois = search_baidumap_poi(company)
    for poi in pois:
        if poi["phone"]:
            for p in extract_phones_from_text(poi["phone"]):
                if p not in all_phones:
                    all_phones.add(p)
                    sources.append({"phone": p, "source": f"百度地图POI/{poi['name']}", "title": poi["name"]})
    if all_phones:
        _log(f"  ✓ 百度地图POI找到电话: {' | '.join(all_phones)}")
    else:
        _log(f"  ✗ 百度地图POI未找到电话")

    # 2. 缩短公司名再搜
    if not all_phones:
        short_name = company.replace("有限公司", "").replace("股份有限公司", "").replace("集团", "").replace("(", "").replace(")", "").replace("（", "").replace("）", "")
        if short_name != company:
            _log(f"2/3 缩短名称查询: {short_name}")
            pois = search_baidumap_poi(short_name)
            for poi in pois:
                if poi["phone"]:
                    for p in extract_phones_from_text(poi["phone"]):
                        if p not in all_phones:
                            all_phones.add(p)
                            sources.append({"phone": p, "source": f"百度地图POI/{poi['name']}", "title": poi["name"]})
            if all_phones:
                _log(f"  ✓ 缩短名称找到电话: {' | '.join(all_phones)}")
            else:
                _log(f"  ✗ 缩短名称也未找到电话")
        else:
            _log(f"2/3 公司名无需缩短，跳过")

    # 3. 顺企网补充
    if not all_phones:
        _log("3/3 顺企网查询中...")
        try:
            key = urllib.parse.quote(company[:6])
            url = f"https://www.11467.com/company/search.php?key={key}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=8)
            html = resp.read().decode("utf-8", errors="replace")
            for p in extract_phones_from_text(html):
                if p not in all_phones:
                    all_phones.add(p)
                    sources.append({"phone": p, "source": "顺企网", "title": ""})
            if all_phones:
                _log(f"  ✓ 顺企网找到电话: {' | '.join(all_phones)}")
            else:
                _log(f"  ✗ 顺企网未找到电话")
        except Exception as _ex:
            _log(f"  ✗ 顺企网查询失败: {str(_ex)[:40]}")
            logger.debug(f"顺企网查询失败: {_ex}")

    return {
        "company": company,
        "phones": sorted(all_phones),
        "phone_count": len(all_phones),
        "sources": sources,
        "steps": steps if steps else [],
    }
