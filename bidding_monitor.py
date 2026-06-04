"""BDSS 招标监控引擎 v2 — 4 种采集策略覆盖多源招标网站"""
from typing import Optional, List
import logging
import json
import re
import sqlite3
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "bidding_monitor.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


# ============ 工具函数 ============

def _decode(raw: bytes) -> str:
    for enc in ["utf-8", "gbk", "gb2312", "gb18030"]:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _get(url: str, timeout: int = 8, headers: Optional[dict] = None) -> str | None:
    h = {**HEADERS, **(headers or {})}
    try:
        req = urllib.request.Request(url, headers=h)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return _decode(resp.read())
    except Exception as e:
        logger.debug(f"GET failed: {url[:60]} → {e}")
        return None


def _post(url: str, data: dict, timeout: int = 10, headers: Optional[dict] = None) -> str | None:
    h = {**HEADERS, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", **(headers or {})}
    try:
        body = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=h)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return _decode(resp.read())
    except Exception as e:
        logger.debug(f"POST failed: {url[:60]} → {e}")
        return None


def extract_phones(text: str) -> list[str]:
    phones = set()
    for m in re.finditer(r"1[3-9]\d{9}", text):
        phones.add(m.group())
    for m in re.finditer(r"0\d{2,3}[-]?\d{7,8}", text):
        phones.add(m.group().replace("-", ""))
    return sorted(phones)


# ============ 采集器 1: ccgp_search (中国政府采购网) ============

def collect_ccgp(keyword: str, max_pages: int = 2) -> list[dict]:
    """采集中国政府采购网 http://search.ccgp.gov.cn/bxsearch"""
    results = []
    for page in range(1, max_pages + 1):
        params = {
            "searchtype": "1",
            "page_index": str(page),
            "bidSort": "0",
            "buyerName": "",
            "projectId": "",
            "pinMu": "0",
            "bidType": "0",
            "dbselect": "bidx",
            "kw": keyword,
            "start_time": (datetime.now() - timedelta(days=30)).strftime("%Y:%m:%d"),
            "end_time": datetime.now().strftime("%Y:%m:%d"),
            "timeType": "6",
            "displayZone": "",
            "zoneId": "",
            "pppStatus": "0",
            "agentName": "",
        }
        url = "http://search.ccgp.gov.cn/bxsearch?" + urllib.parse.urlencode(params)
        time.sleep(2)  # 反爬
        html = _get(url, timeout=10, headers={"Cookie": "test=1", "Referer": "http://search.ccgp.gov.cn/"})
        if not html:
            break
        if "频繁访问" in html or "访问过于频繁" in html:
            logger.warning("CCGP 限流，等待 10 秒...")
            time.sleep(10)
            html = _get(url, timeout=10)
            if not html or "频繁访问" in html:
                break
        # 解析结果
        blocks = re.findall(r"<li[^>]*>.*?</li>", html, re.DOTALL)
        for block in blocks:
            m = re.search(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, re.DOTALL)
            if not m:
                continue
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            href = m.group(1)
            if not href.startswith("http"):
                href = "http://www.ccgp.gov.cn" + href if href.startswith("/") else href
            if "bxsearch" in href or "znzxsearch" in href:
                continue
            text = re.sub(r"<[^>]+>", " ", block)
            buyer_m = re.search(r"采购人[：:]\s*([^\n<|]+)", text)
            results.append({
                "title": title,
                "url": href,
                "source": "中国政府采购网",
                "buyer": buyer_m.group(1).strip() if buyer_m else "",
                "phone": "",
            })
        if len(blocks) < 5:
            break  # 无更多数据
    return results


# ============ 采集器 2: ggzy_search (全国公共资源交易平台) ============

def collect_ggzy(keyword: str, max_pages: int = 2) -> list[dict]:
    """采集全国公共资源交易平台 https://deal.ggzy.gov.cn"""
    results = []
    endpoint = "https://deal.ggzy.gov.cn/ds/deal/dealList_find.jsp"
    since = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    until = datetime.now().strftime("%Y-%m-%d")
    business_types = [
        {"label": "政府采购", "deal_classify": "02", "deal_stage": "0201"},
        {"label": "工程建设", "deal_classify": "01", "deal_stage": "0101"},
    ]
    for biz in business_types:
        for page in range(1, max_pages + 1):
            data = {
                "TIMEBEGIN_SHOW": since,
                "TIMEEND_SHOW": until,
                "TIMEBEGIN": since,
                "TIMEEND": until,
                "SOURCE_TYPE": "1",
                "DEAL_TIME": "06",
                "DEAL_CLASSIFY": biz["deal_classify"],
                "DEAL_STAGE": biz["deal_stage"],
                "DEAL_PROVINCE": "0",
                "DEAL_CITY": "0",
                "DEAL_PLATFORM": "0",
                "BID_PLATFORM": "0",
                "DEAL_TRADE": "0",
                "isShowAll": "1",
                "PAGENUMBER": str(page),
                "FINDTXT": keyword,
            }
            html = _post(endpoint, data, timeout=10,
                         headers={"Referer": "https://www.ggzy.gov.cn/deal/dealList.html",
                                  "Origin": "https://www.ggzy.gov.cn",
                                  "X-Requested-With": "XMLHttpRequest"})
            if not html:
                continue
            try:
                payload = json.loads(html)
            except json.JSONDecodeError:
                # 有时返回 HTML 格式错误
                m = re.search(r"\{.*\}", html, re.DOTALL)
                if m:
                    payload = json.loads(m.group(0))
                else:
                    break
            rows = payload.get("data") or []
            for row in rows:
                title = row.get("title") or row.get("name", "")
                url = row.get("url") or row.get("href") or row.get("detailUrl", "")
                title = re.sub(r"<[^>]+>", "", title).strip()
                results.append({
                    "title": title,
                    "url": url if url.startswith("http") else "https://www.ggzy.gov.cn" + url if url.startswith("/") else url,
                    "source": f"全国公共资源平台/{biz['label']}",
                    "buyer": row.get("buyer", "") or row.get("purchaser", "") or "",
                    "phone": "",
                })
            if not rows:
                break
    return results


# ============ 采集器 3: rss_search (Bing RSS 搜索) ============

def collect_rss(keyword: str, allowed_domains: Optional[list[str]] = None) -> list[dict]:
    """通过 Bing RSS 搜索招标信息"""
    results = []
    query_templates = [
        '"{keyword}" 招标',
        '"{keyword}" 采购',
        '"{keyword}" 投标',
    ]
    seen_urls = set()
    for qt in query_templates:
        query = qt.format(keyword=keyword)
        feed_url = f"https://www.bing.com/search?format=rss&q={urllib.parse.quote(query)}"
        xml_text = _get(feed_url, timeout=8)
        if not xml_text:
            continue
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            continue
        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            if title_el is None or link_el is None or title_el.text is None or link_el.text is None:
                continue
            title = title_el.text.strip()
            url = link_el.text.strip()
            if url in seen_urls:
                continue
            seen_urls.add(url)
            # 域名过滤
            if allowed_domains:
                from urllib.parse import urlparse
                host = urlparse(url).netloc.lower()
                if not any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed_domains):
                    continue
            desc = re.sub(r"<[^>]+>", "", (desc_el.text or "")).strip()[:200] if desc_el else ""
            phones = extract_phones(desc + title)
            results.append({
                "title": title,
                "url": url,
                "source": "Bing搜索",
                "buyer": "",
                "phone": " | ".join(phones[:3]),
            })
    return results[:30]


# ============ 采集器 4: html_list (定点抓取列表页) ============

def collect_html_list(url: str, source_name: str = "招标列表",
                      link_min_len: int = 8,
                      max_items: int = 30) -> list[dict]:
    """采集指定 HTML 列表页的链接"""
    results = []
    html = _get(url, timeout=10)
    if not html:
        return results
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        href = m.group(1)
        if len(title) < link_min_len:
            continue
        if not href.startswith("http"):
            continue
        phones = extract_phones(title)
        results.append({
            "title": title,
            "url": href,
            "source": source_name,
            "buyer": "",
            "phone": " | ".join(phones[:3]),
        })
    return results[:max_items]


# ============ 详情页电话提取 ============

def extract_detail_phone(url: str) -> dict:
    """打开招标详情页，提取联系人、电话、采购单位"""
    result = {"buyer": "", "contact": "", "phone": "", "email": ""}
    if not url or not url.startswith("http"):
        return result
    html = _get(url, timeout=10)
    if not html:
        return result

    # 提取采购单位/采购人
    for pattern in [r"采购人[：:]\s*([^\n<,，]{2,40})",
                    r"采购单位[：:]\s*([^\n<,，]{2,40})",
                    r"招标人[：:]\s*([^\n<,，]{2,40})",
                    r"业主[：:]\s*([^\n<,，]{2,40})"]:
        m = re.search(pattern, html)
        if m:
            result["buyer"] = m.group(1).strip()
            break

    # 提取联系人
    for pattern in [r"联系人[：:]\s*([^\n<,，]{2,10})",
                    r"项目联系人[：:]\s*([^\n<,，]{2,10})"]:
        m = re.search(pattern, html)
        if m:
            result["contact"] = m.group(1).strip()
            break

    # 提取电话（内联正则，保持模块自包含）
    phones = set()
    for m in re.finditer(r"(?<!\d)1[3-9]\d{9}(?!\d)", html):
        phones.add(m.group())
    for m in re.finditer(r"0\d{2,3}[-\s]?\d{7,8}", html):
        phones.add(m.group().replace(" ", "-"))
    for m in re.finditer(r"(?:400|800)[-\s]?\d{3}[-\s]?\d{4}", html):
        phones.add(m.group().replace(" ", "-"))
    if phones:
        result["phone"] = " | ".join(sorted(phones)[:3])

    # 提取邮箱
    m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html)
    if m:
        result["email"] = m.group(0)

    return result


# ============ 批量扫描 ============

# 行业关键词 — 水处理药剂
WATER_CHEM_KEYWORDS = [
    # 水处理药剂核心词
    "水处理药剂", "阻垢剂", "杀菌剂", "缓蚀剂", "絮凝剂",
    "循环水处理", "反渗透药剂",
    "冷却水处理", "清洗预膜",
    # 行业场景词
    "电厂药剂", "污水处理药剂", "锅炉水处理",
    # 采购方式词
    "水处理剂 采购", "水处理 招标",
]
def ai_analyze_bidding(title: str, buyer: str = "") -> dict:
    """用 AI 分析招标线索的相关性"""
    from utils.env import get_ai_api_key, get_ai_model
    api_key = get_ai_api_key()
    if not api_key:
        return {"relevance": 0, "reason": "", "products": []}
    from skills.ai import AISearch
    ai = AISearch(api_key=api_key, model=get_ai_model())
    prompt = ('分析是否与水处理药剂行业相关\n标题: ' + title + '\n采购方: ' + buyer +
              '\nJSON: {"relevance":0-10,"reason":"理由","products":["产品"]}\n只返回JSON')
    content = ai._call_llm([{"role": "system", "content": "水处理行业顾问，返回严格JSON"},
                           {"role": "user", "content": prompt}])
    if content:
        import re as _re
        m = _re.search(r'\{.*\}', content, _re.DOTALL)
        if m:
            try:
                return __import__('json').loads(m.group(0))
            except Exception:
                pass
    return {"relevance": 0, "reason": "", "products": []}

CCGP_KEYWORDS = ["水处理药剂", "阻垢剂", "杀菌剂", "循环水处理", "电厂药剂"]


CCGP_KEYWORDS = ["水处理药剂", "阻垢剂", "杀菌剂", "循环水处理", "电厂药剂"]

# 招标网站配置
BIDDING_SOURCES = [
    # --- 核心政府采购 ---
    {"name": "中国政府采购网", "type": "ccgp", "keywords": WATER_CHEM_KEYWORDS, "max_pages": 1},
    # --- Bibi招标网 ---
    {"name": "比比招标网", "type": "rss",
     "keywords": WATER_CHEM_KEYWORDS[:3],
     "allowed_domains": ["bibenet.com", "qianlima.com"]},
    # --- 招标采购导航网 ---
    {"name": "招标采购导航网", "type": "html",
     "url": "http://www.okcis.cn/search/?q={keyword}&page=1",
     "keywords": WATER_CHEM_KEYWORDS[:3], "max_pages": 1,
     "title_include": ["招标", "采购", "公告", "项目", "中标"],
     "title_exclude": ["Group", "业务办公室", "搜企网", "首页", "登录"]},
]


def scan_all_sources() -> dict:
    """扫描所有配置的招标源"""
    all_items = []
    per_source = []

    # 去重缓存
    title_seen = set()

    for src in BIDDING_SOURCES:
        source_name = src["name"]
        stype = src["type"]
        keywords = src.get("keywords", WATER_CHEM_KEYWORDS)
        max_pages = src.get("max_pages", 1)

        items = []
        try:
            if stype == "ccgp":
                for kw in CCGP_KEYWORDS:
                    items.extend(collect_ccgp(kw, max_pages))
            elif stype == "rss":
                for kw in CCGP_KEYWORDS[:2]:
                    items.extend(collect_rss(kw, src.get("allowed_domains")))
            elif stype == "html":
                url_template = src.get("url", "")
                title_include = src.get("title_include", [])
                title_exclude = src.get("title_exclude", [])
                for kw in OKCIS_KEYWORDS:
                    url = url_template.replace("{keyword}", urllib.parse.quote(kw))
                    raw_items = collect_html_list(url, source_name)
                    for item in raw_items:
                        t = item["title"]
                        if title_include and not any(k in t for k in title_include):
                            continue
                        if title_exclude and any(k in t for k in title_exclude):
                            continue
                        items.append(item)
        except Exception as e:
            logger.error(f"Source failed: {source_name}: {e}")

        # 去重
        seen = set()
        deduped = []
        for item in items:
            key = item["title"][:60]
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        items = deduped

        all_items.extend(items)
        per_source.append({"source": source_name, "found": len(items)})
        logger.info(f"  {source_name}: {len(items)} 条")

    return {"items": all_items, "per_source": per_source, "total": len(all_items)}


_db_conn = None

def get_db() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is not None:
        return _db_conn
    _db_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _db_conn.execute("""
        CREATE TABLE IF NOT EXISTS bidding_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT DEFAULT '',
            source TEXT DEFAULT '',
            buyer TEXT DEFAULT '',
            contact TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            matched_at REAL NOT NULL,
            status TEXT DEFAULT 'new',
            relevance INTEGER DEFAULT 0,
            notes TEXT DEFAULT ''
        )
    """)
    # 数据库迁移：旧表缺少 relevance 列时补充
    try:
        _db_conn.execute("SELECT relevance FROM bidding_items LIMIT 1")
    except Exception:
        _db_conn.execute("ALTER TABLE bidding_items ADD COLUMN relevance INTEGER DEFAULT 0")
    _db_conn.execute("""
        CREATE TABLE IF NOT EXISTS monitor_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_found INTEGER DEFAULT 0,
            sources TEXT DEFAULT '[]'
        )
    """)
    _db_conn.commit()
    # 数据库迁移：旧表缺少 scanned_at 列时补充
    try:
        _db_conn.execute("SELECT scanned_at FROM monitor_log LIMIT 1")
    except Exception:
        _db_conn.execute("ALTER TABLE monitor_log ADD COLUMN scanned_at REAL NOT NULL DEFAULT 0")
    return _db_conn

# 模块加载时初始化数据库表
get_db()

def save_items(items: list[dict]) -> int:
    """保存条目并抓取详情页电话，返回新增数"""
    conn = get_db()
    new_count = 0
    for i, item in enumerate(items):
        title = item.get("title", "")
        phone = item.get("phone", "")
        buyer = item.get("buyer", "")
        exists = conn.execute(
            "SELECT id, phone FROM bidding_items WHERE title=? AND source=?",
            (title[:80], item.get("source", "")),
        ).fetchone()
        if not exists:
            # AI 分析相关性
            try:
                relevance = ai_analyze_bidding(title).get("relevance", 0)
            except Exception:
                relevance = 0
            
            detail = {"contact": "", "email": ""}
            if i < 10 and item.get("url"):
                detail = extract_detail_phone(item["url"])
                if not phone:
                    phone = detail.get("phone", "")
                if not buyer:
                    buyer = detail.get("buyer", "")
            # 如果详情页没找到电话，从标题提取公司名查百度地图
            if not phone and buyer:
                from skills.lite_search import search_baidumap_poi
                try:
                    pois = search_baidumap_poi(buyer)
                    map_phones = set()
                    for p in pois:
                        if p.get("phone"):
                            for m in re.finditer(r"1[3-9]\d{9}", p["phone"]):
                                map_phones.add(m.group())
                            for m in re.finditer(r"0\d{2,3}[-]?\d{7,8}", p["phone"]):
                                map_phones.add(m.group().replace("-", ""))
                    if map_phones:
                        phone = " | ".join(sorted(map_phones)[:3])
                except Exception:
                    pass
            conn.execute(
                "INSERT INTO bidding_items (title, url, source, buyer, contact, phone, email, matched_at, status, relevance) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)",
                (title[:200], item.get("url", ""), item.get("source", ""),
                 buyer, detail.get("contact", ""), phone, detail.get("email", ""), time.time(), relevance),
            )
            new_count += 1
    conn.commit()
    return new_count


def log_scan(total_found: int, per_source: list[dict]):
    conn = get_db()
    conn.execute(
        "INSERT INTO monitor_log (scanned_at, total_found, sources) VALUES (?, ?, ?)",
        (time.time(), total_found, json.dumps(per_source, ensure_ascii=False)),
    )
    conn.commit()

def get_stats() -> dict:
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM bidding_items").fetchone()[0]
    new_ = conn.execute("SELECT COUNT(*) FROM bidding_items WHERE status='new'").fetchone()[0]
    contacted = conn.execute("SELECT COUNT(*) FROM bidding_items WHERE status='contacted'").fetchone()[0]
    recent = conn.execute(
        "SELECT id, title, source, buyer, contact, phone, email, matched_at, status, relevance FROM bidding_items ORDER BY matched_at DESC LIMIT 30"
    ).fetchall()
    logs = conn.execute(
        "SELECT scanned_at, total_found, sources FROM monitor_log ORDER BY scanned_at DESC LIMIT 10"
    ).fetchall()
    return {
        "total": total, "new": new_, "contacted": contacted,
        "recent": [{"id": r[0], "title": r[1], "source": r[2], "buyer": r[3],
                     "contact": r[4], "phone": r[5], "email": r[6],
                     "time": r[7], "status": r[8], "relevance": r[9]} for r in recent],
        "logs": [{"time": r[0], "found": r[1], "sources": json.loads(r[2])} for r in logs],
    }

def update_status(item_id: int, status: str, notes: str = ""):
    conn = get_db()
    conn.execute("UPDATE bidding_items SET status=?, notes=? WHERE id=?", (status, notes, item_id))
    conn.commit()


# ============ 主入口 ============

def close_db():
    global _db_conn
    if _db_conn:
        _db_conn.close()
        _db_conn = None



def send_wechat_notification(title: str, content: str, send_key: str = "") -> bool:
    """通过 Server酱 推送微信通知"""
    if not send_key:
        send_key = os.environ.get("BDSS_WECHAT_SENDKEY", "")
    if not send_key:
        logger.debug("未配置 BDSS_WECHAT_SENDKEY，跳过微信通知")
        return False
    url = f"https://sctapi.ftqq.com/{send_key}.send"
    try:
        data = urllib.parse.urlencode({"title": title, "desp": content}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result.get("code") == 0
    except Exception as e:
        logger.warning(f"微信通知失败: {e}")
        return False


def scan_with_notify() -> dict:
    """扫描并发送微信通知"""
    from pathlib import Path
    env_path = Path(__file__).parent / ".env"
    send_key = ""
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("BDSS_WECHAT_SENDKEY="):
                send_key = line.split("=", 1)[1].strip().strip("'\"")

    result = scan()
    if result["new_saved"] > 0 and send_key:
        title = f'BDSS: 发现 {result["new_saved"]} 条新招标'
        lines = [f"### {title}\n"]
        for s in result["per_source"]:
            if s["found"] > 0:
                lines.append(f"- {s['source']}: {s['found']} 条")
        send_wechat_notification(title, "\n".join(lines), send_key)
    return result

def scan() -> dict:
    """执行一次完整扫描"""
    result = scan_all_sources()
    new_count = save_items(result["items"])
    log_scan(result["total"], result["per_source"])
    return {
        "total_found": result["total"],
        "new_saved": new_count,
        "per_source": result["per_source"],
    }
