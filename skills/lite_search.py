"""轻量搜索模块 — 公司电话一站式搜索"""
import json
import logging
import os
import re
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

from skills.engines import search_bing, search_baidu, fetch_page_text

logger = logging.getLogger(__name__)

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
        from utils.env import get_ak
        ak = get_ak()
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

    # 招标数据库查缓存（已有的线索中可能已有电话）
    _log(f"0/4 招标数据库查询: {company}")
    try:
        from bidding_monitor import get_db, close_db
        _conn = get_db()
        _rows = _conn.execute(
            "SELECT phone FROM bidding_items WHERE (buyer LIKE ? OR title LIKE ?) AND phone != '' ORDER BY matched_at DESC LIMIT 5",
            (f"%{company}%", f"%{company}%"),
        ).fetchall()
        if _rows:
            for _r in _rows:
                for p in extract_phones_from_text(_r[0]):
                    all_phones.add(p)
                    sources.append({"phone": p, "source": "招标数据库", "title": ""})
            _log(f"  ✓ 招标数据库找到电话: {' | '.join(all_phones)}")
        else:
            _log(f"  - 招标数据库未找到")
    except:
        _log(f"  - 招标数据库查询跳过")

    # 1. 百度地图 POI（最准）
    _log(f"1/4 百度地图POI查询: {company}")
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

        except Exception as _ex:
            _log(f"  ✗ 顺企网查询失败: {str(_ex)[:40]}")
            logger.debug(f"顺企网查询失败: {_ex}")

    # 4. 网页搜索：搜"公司名 联系电话"并打开结果页
    if not all_phones:
        queries = [f"{company} 联系电话", f"{company} 电话", f"{company} 联系方式"]
        for i, q in enumerate(queries[:2]):
            _log(f"4/{3+i+1} 搜索: \"{q}\"")
            try:
                results = search_bing(q, max_results=3)
                if not results:
                    results = search_baidu(q, max_results=3)
                if not results:
                    _log(f"  ✗ 搜索引擎无结果")
                    continue
                for r in results:
                    page_text = fetch_page_text(r["url"])
                    text = r.get("snippet", "") + " " + page_text
                    for p in extract_phones_from_text(text):
                        if p not in all_phones:
                            all_phones.add(p)
                            sources.append({"phone": p, "source": r["url"][:50], "title": r["title"][:40]})
                    if all_phones:
                        break
                if all_phones:
                    _log(f"  ✓ 搜索找到电话: {' | '.join(all_phones)}")
                else:
                    _log(f"  ✗ 搜索未找到电话")
            except Exception as ex:
                _log(f"  ✗ 搜索异常: {str(ex)[:40]}")

    # 5. AI 搜索验证（无论前面是否找到都执行）
    _log(f"5/5 AI搜索: {company}")
    try:
        from skills.ai import AISearch
        ai = AISearch()
        results = ai.search(company, max_results=3)
        for r in results:
            snip = r.get("snippet", "")
            if snip:
                for p in extract_phones_from_text(snip):
                    if p not in all_phones:
                        all_phones.add(p)
                        sources.append({"phone": p, "source": "AI搜索", "title": r.get("title", "")})
        if all_phones:
            _log("  ok AI找到: " + " | ".join(all_phones))
        _log(f"  ✗ AI搜索未找到电话")
    except Exception as _ex:
        _log(f"  ✗ AI搜索失败: {str(_ex)[:40]}")

    # 标记来源可信度
    confidence_map = {
        "招标数据库": "high",
        "百度地图POI": "high",
        "顺企网": "medium",
        "AI搜索": "medium",
    }
    for s in sources:
        matched = False
        for prefix, level in confidence_map.items():
            if s["source"].startswith(prefix):
                s["confidence"] = level
                matched = True
                break
        if not matched:
            s["confidence"] = "low"

    return {
        "phones": sorted(all_phones),
        "phone_count": len(all_phones),
        "sources": sources,
        "steps": steps if steps else [],
    }
