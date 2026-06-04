"""BDSS 招标监控引擎 — 多源扫描 + 关键词匹配 + 持久化"""
import json
import logging
import re
import sqlite3
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "bidding_monitor.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# ============ 数据源配置 ============

SOURCES = [
    {
        "id": "okcis",
        "name": "招标采购导航网",
        "type": "search",
        "url_template": "https://www.okcis.cn/search?q={keyword}&page={page}",
        "parser": "okcis",
        "priority": 1,
    },
    {
        "id": "baidumap",
        "name": "百度地图 POI",
        "type": "api",
        "url_template": "https://api.map.baidu.com/place/v2/search?query={keyword}&region=全国&output=json&ak={ak}",
        "parser": "baidumap",
        "priority": 2,
    },
]


# ============ 解析器 ============

def parse_okcis(html: str) -> list[dict]:
    """解析招标采购导航网"""
    items = []
    # 提取招标条目标题+链接
    for m in re.finditer(r'<div class="tit">\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        url = m.group(1)
        if not url.startswith("http"):
            url = "https://www.okcis.cn" + url
        items.append({"title": title, "url": url, "source": "招标采购导航网"})
    # 提取结果列表中的联系人
    for m in re.finditer(r"联系人[：:]\s*([^<\n,，]{2,10})", html):
        items.append({"title": f"联系人: {m.group(1).strip()}", "url": "", "source": "招标采购导航网"})
    return items


def parse_baidumap(html: str) -> list[dict]:
    """解析百度地图 API 响应"""
    items = []
    try:
        data = json.loads(html)
        for poi in data.get("results", []):
            name = poi.get("name", "")
            address = poi.get("address", "")
            phone = poi.get("telephone", "") or poi.get("phone", "")
            if name:
                items.append({
                    "title": f"{name} {'- ' + phone if phone else ''}",
                    "url": "",
                    "source": "百度地图POI",
                    "address": address,
                    "phone": phone,
                })
    except Exception:
        pass
    return items


def parse_generic(html: str) -> list[dict]:
    """通用解析器 — 提取所有链接和电话"""
    items = []
    # 提取含关键词的链接
    for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        url = m.group(1)
        if len(title) > 5 and not url.startswith("javascript"):
            items.append({"title": title, "url": url, "source": "通用"})
    return items


PARSERS = {
    "okcis": parse_okcis,
    "baidumap": parse_baidumap,
    "generic": parse_generic,
}


# ============ 数据库 ============

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bidding_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT DEFAULT '',
            source TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            matched_at REAL NOT NULL,
            status TEXT DEFAULT 'new',
            notes TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS monitor_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            scanned_at REAL NOT NULL,
            items_found INTEGER DEFAULT 0,
            new_items INTEGER DEFAULT 0,
            error TEXT DEFAULT ''
        )
    """)
    conn.commit()
    return conn


def save_items(items: list[dict], keywords: str, source_id: str) -> int:
    """保存新条目到数据库，返回新增数"""
    conn = get_db()
    new_count = 0
    for item in items:
        title = item.get("title", "")
        phone = item.get("phone", "")
        # 去重
        exists = conn.execute(
            "SELECT id FROM bidding_items WHERE title=? AND source=?",
            (title[:80], item.get("source", "")),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO bidding_items (title, url, source, keywords, phone, matched_at) VALUES (?, ?, ?, ?, ?, ?)",
                (title[:200], item.get("url", ""), item.get("source", ""), keywords, phone, time.time()),
            )
            new_count += 1
    conn.commit()
    return new_count


def log_scan(source_id: str, items_found: int, new_items: int, error: str = ""):
    conn = get_db()
    conn.execute(
        "INSERT INTO monitor_log (source_id, scanned_at, items_found, new_items, error) VALUES (?, ?, ?, ?, ?)",
        (source_id, time.time(), items_found, new_items, error),
    )
    conn.commit()


def get_stats() -> dict:
    """获取监控统计数据"""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM bidding_items").fetchone()[0]
    new = conn.execute("SELECT COUNT(*) FROM bidding_items WHERE status='new'").fetchone()[0]
    contacted = conn.execute("SELECT COUNT(*) FROM bidding_items WHERE status='contacted'").fetchone()[0]
    recent = conn.execute("SELECT title, source, matched_at, status, phone FROM bidding_items ORDER BY matched_at DESC LIMIT 20").fetchall()
    logs = conn.execute("SELECT source_id, scanned_at, items_found, new_items FROM monitor_log ORDER BY scanned_at DESC LIMIT 10").fetchall()
    return {
        "total": total,
        "new": new,
        "contacted": contacted,
        "recent": [{"title": r[0], "source": r[1], "time": r[2], "status": r[3], "phone": r[4]} for r in recent],
        "logs": [{"source": r[0], "time": r[1], "found": r[2], "new": r[3]} for r in logs],
    }


def update_status(item_id: int, status: str, notes: str = ""):
    conn = get_db()
    conn.execute("UPDATE bidding_items SET status=?, notes=? WHERE id=?", (status, notes, item_id))
    conn.commit()


# ============ 扫描引擎 ============

def scan_keyword(keyword: str, ak: str = "") -> dict:
    """扫描所有数据源，返回新增条目数"""
    total_new = 0
    results = []

    for src in SOURCES:
        source_id = src["id"]
        parser = PARSERS.get(src["parser"])
        if not parser:
            continue

        try:
            # 构建 URL
            url = src["url_template"].format(keyword=urllib.parse.quote(keyword), ak=ak, page=1)
            req = urllib.request.Request(url, headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=5)
            html = resp.read().decode("utf-8", errors="replace")

            # 解析结果
            items = parser(html)
            items_found = len(items)
            new_items = save_items(items, keyword, source_id)

            log_scan(source_id, items_found, new_items)
            total_new += new_items
            results.append({"source": src["name"], "found": items_found, "new": new_items})

        except Exception as e:
            log_scan(source_id, 0, 0, str(e)[:100])
            results.append({"source": src["name"], "found": 0, "new": 0, "error": str(e)[:50]})

        time.sleep(1)  # 礼貌延迟

    return {"total_new": total_new, "results": results}


def scan_keywords(keywords: list[str], ak: str = "") -> dict:
    """扫描多个关键词"""
    total = 0
    per_keyword = []
    for kw in keywords:
        r = scan_keyword(kw, ak)
        per_keyword.append({"keyword": kw, "new": r["total_new"]})
        total += r["total_new"]
    return {"total_new": total, "per_keyword": per_keyword}
