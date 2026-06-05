"""轻量搜索模块 — 公司电话一站式搜索（采集器编排层）

search_company_phones() 按优先级依次调用各采集器，合并去重后返回结果。
各采集器位于 collectors/ 目录，互相独立，可单独替换或禁用。
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ===== 向后兼容的工具函数 =====

_PHONE_EXTRACTOR = None


def extract_phones_from_text(text: str) -> list[str]:
    """从文本中提取中国电话号码（委托 PhoneExtractor）"""
    global _PHONE_EXTRACTOR
    if _PHONE_EXTRACTOR is None:
        from extractors.phone import PhoneExtractor
        _PHONE_EXTRACTOR = PhoneExtractor(prefer_nearby=False)
    return _PHONE_EXTRACTOR.extract(text)


def search_baidumap_poi(company: str) -> list[dict]:
    """通过百度地图 Place API 搜索公司 POI 及电话（向后兼容接口）"""
    from collectors.baidu_poi import BaiduPOICollector
    collector = BaiduPOICollector()
    result = collector.collect(company)
    # 转换为旧格式的 list[dict]
    pois = []
    for src in result.get("sources", []):
        pois.append({
            "name": src.get("title", company),
            "address": "",
            "phone": src.get("phone", ""),
            "uid": "",
        })
    return pois


def search_bidding(keyword: str, max_pages: int = 1) -> dict:
    """从招标采购导航网搜招标公告，提取电话（独立工具函数）"""
    import re
    import urllib.request
    import urllib.parse

    SEARCH_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
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
    return {"phones": sorted(all_phones), "phone_count": len(all_phones),
            "items": items[:10], "source": "招标采购导航网"}


# ===== 核心编排函数 =====

def search_company_phones(company: str, log_detail: bool = False) -> dict:
    """
    一站式搜索公司电话 — 采集器编排入口。

    按优先级依次调用各采集器：
      0/5  招标数据库（缓存线索）
      1/5  百度地图 POI（含缩短名称重试）
      2/5  顺企网
      3/5  网页搜索（Bing / 百度）
      4/5  AI 搜索验证（始终执行）

    采集到电话后跳过后续步骤（AI验证除外，始终执行）。
    返回: {"phones": [...], "phone_count": N, "sources": [...], "steps": [...]}
    """
    from collectors import COLLECTORS

    all_phones: set = set()
    all_sources: list = []
    steps: list = [] if log_detail else None

    def _log(msg: str):
        if steps is not None:
            steps.append(msg)

    total = len(COLLECTORS)

    for idx, collector_cls in enumerate(COLLECTORS):
        collector = collector_cls()
        name = collector.name

        _log(f"{idx}/{total - 1} {name}: {company}")

        try:
            result = collector.collect(company, existing_phones=all_phones)
        except Exception as e:
            _log(f"  ✗ {name} 异常: {str(e)[:60]}")
            logger.debug(f"{name} collector 异常: {e}")
            continue

        new_phones = result.get("phones", set())
        new_sources = result.get("sources", [])
        log_msg = result.get("log", "")

        if new_phones:
            before = len(all_phones)
            all_phones.update(new_phones)
            all_sources.extend(new_sources)
            added = len(all_phones) - before
            _log(f"  ✓ {name} 新增 {added} 个电话: {' | '.join(sorted(new_phones))}")
        else:
            _log(f"  ✗ {name} 未找到电话" + (f" — {log_msg}" if log_msg else ""))
            if new_sources:
                all_sources.extend(new_sources)

    # 如果 AI 验证从已有来源中补充了号码，加入 all_phones
    for src in all_sources:
        phone = src.get("phone", "")
        if phone:
            all_phones.add(phone)

    return {
        "phones": sorted(all_phones),
        "phone_count": len(all_phones),
        "sources": all_sources,
        "steps": steps if steps else [],
    }
