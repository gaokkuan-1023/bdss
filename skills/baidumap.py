"""百度地图 Skill — 查询公司 POI 信息提取电话"""

import sys, time, json, re, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from extractors.phone import PhoneExtractor


def query_baidu_map_poi(company: str) -> dict:
    """
    通过百度地图查询公司 POI 信息。
    返回: {"name","address","phone","uid","source"}
    """
    extractor = PhoneExtractor(prefer_nearby=True)
    result = {"name": company, "address": "", "phone": "", "uid": "", "source": "", "all_phones": []}

    # ===== 方法1: 用 Playwright 拦截 API 响应 =====
    try:
        phones, info = _intercept_map_api(company)
        if phones:
            result["all_phones"] = phones
            result["phone"] = phones[0]
            result["source"] = "百度地图API"
            if info.get("name"):
                result["name"] = info["name"]
            if info.get("address"):
                result["address"] = info["address"]
            return result
    except Exception as e:
        print(f"    [!] API拦截失败: {e}")

    # ===== 方法2: 手机版百度地图搜索 =====
    try:
        phones, addr = _mobile_map_search(company)
        if phones:
            result["all_phones"] = phones
            result["phone"] = phones[0]
            result["source"] = "手机百度地图"
            if addr:
                result["address"] = addr
            return result
    except Exception as e:
        print(f"    [!] 手机版搜索失败: {e}")

    return result


def _intercept_map_api(company: str) -> tuple:
    """
    打开百度地图搜索页，拦截 POI 数据 API 响应。
    """
    captured_data = []
    encoded = urllib.parse.quote(company)

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )

        # 尝试 stealth
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(ctx)
        except Exception:
            pass

        page = ctx.new_page()
        page.set_default_timeout(30000)

        # 拦截 API 响应
        api_responses = []

        def on_response(resp):
            url = resp.url
            # 捕获 POI 搜索关键词与详情API
            if any(k in url for k in ['/su?', 'qt=ninf', 'poilist', 'searchbox']):
                try:
                    data = resp.json()
                    api_responses.append({"url": url[:120], "data": data})
                except Exception:
                    pass

        page.on("response", on_response)

        # 打开搜索页（直接搜索公司名）
        page.goto(f"https://map.baidu.com/search/{encoded}",
                  wait_until="networkidle")
        page.wait_for_timeout(3000)

        b.close()

    # 解析捕获的API数据
    extractor = PhoneExtractor(prefer_nearby=True)
    all_phones = set()
    info = {}

    for resp in api_responses:
        data = resp.get("data", {})
        text = json.dumps(data, ensure_ascii=False)

        # 提取电话
        phones = extractor.extract(text)
        for p in phones:
            all_phones.add(p)

        # 提取地址/名称
        if isinstance(data, dict):
            content = data.get("content") or data.get("result") or data
            if isinstance(content, dict):
                if content.get("name") and not info.get("name"):
                    info["name"] = content["name"]
                if content.get("addr") and not info.get("address"):
                    info["address"] = content["addr"]

    if all_phones or info.get("address"):
        return sorted(all_phones), info
    return [], {}


def _mobile_map_search(company: str) -> tuple:
    """
    用手机版百度地图搜索公司。
    """
    encoded = urllib.parse.quote(company)
    extractor = PhoneExtractor(prefer_nearby=True)

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0) AppleWebKit/605.1.15 Mobile/15E148",
            viewport={"width": 390, "height": 844},
            locale="zh-CN",
        )
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(ctx)
        except Exception:
            pass

        page = ctx.new_page()
        page.set_default_timeout(20000)

        try:
            page.goto(f"https://map.baidu.com/search/{encoded}",
                      wait_until="domcontentloaded")
        except Exception:
            pass
        page.wait_for_timeout(5000)

        text = page.evaluate("() => document.body.innerText")
        b.close()

    phones = extractor.extract(text)

    # 提取地址
    addr = ""
    for line in text.split("\n"):
        if "地址" in line or "位置" in line:
            m = re.search(r"地址[：:]\s*(.+)", line)
            if m:
                addr = m.group(1).strip()
                break

    return phones, addr


if __name__ == "__main__":
    import sys
    company = sys.argv[1] if len(sys.argv) > 1 else "山东金泉水处理有限公司"
    print(f"\n{'='*50}")
    print(f"[百度地图 POI 查询] {company}")
    print(f"{'='*50}")

    r = query_baidu_map_poi(company)

    print(f"\n  名称: {r.get('name', '')}")
    print(f"  地址: {r.get('address', '')}")
    print(f"  来源: {r.get('source', '无')}")
    print(f"\n  电话:")
    if r.get('all_phones'):
        for p in r['all_phones']:
            print(f"    [电话] {p}")
    else:
        print(f"    未找到")
