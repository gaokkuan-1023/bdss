"""HTTP 搜索引擎模块 — Bing + Baidu 网页搜索"""

import json
import logging
import re
import urllib.request
import urllib.parse

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def search_bing(query: str, max_results: int = 5) -> list[dict]:
    """通过 HTTP 请求搜必应"""
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={max_results}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Bing 搜索失败: {e}")
        return []

    results = []
    for m in re.finditer(r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>.*?<h2>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        url_val = m.group(1)
        if title and url_val and len(results) < max_results:
            results.append({"title": title, "url": url_val, "snippet": "", "index": len(results) + 1})
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
    for m in re.finditer(r'<h3[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        url_val = m.group(1)
        if not url_val.startswith("http"):
            url_match = re.search(r"url=([^&]+)", url_val)
            if url_match:
                try:
                    url_val = urllib.parse.unquote(url_match.group(1))
                except Exception:
                    pass
        if title and len(results) < max_results:
            results.append({"title": title, "url": url_val, "snippet": "", "index": len(results) + 1})
    return results


def fetch_page_text(url: str, timeout: int = 15) -> str:
    """获取页面纯文本"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        html = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()[:10000]
    except Exception:
        return ""
