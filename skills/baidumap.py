"""百度地图 Skill v2 — 通过内部 API 直接查询 POI 电话"""

import sys, json, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from extractors.phone import PhoneExtractor

_BASE = "https://map.baidu.com"


def query_baidu_map_poi(company: str) -> dict:
    """
    通过百度地图内部 API 查询公司 POI 电话。
    策略: Playwright + JS fetch 调用内部 API
    """
    result = {"name": company, "address": "", "phone": "", "uid": "",
              "source": "", "all_phones": []}
    extractor = PhoneExtractor(prefer_nearby=True)

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        page.set_default_timeout(30000)

        # 直接打开搜索结果的静态页面
        wd = urllib.parse.quote(company)
        search_url = f"{_BASE}/search/{wd}"
        print(f"    [百度地图] 打开: {search_url}")
        try:
            page.goto(search_url, wait_until="networkidle")
        except Exception:
            pass  # 超时继续
        page.wait_for_timeout(5000)

        # 获取页面渲染文本
        text = page.evaluate("() => document.body.innerText")
        if not text:
            b.close()
            return result

        # 提取电话
        phones = extractor.extract(text)
        result["all_phones"] = phones
        if phones:
            result["phone"] = phones[0]
            result["source"] = "百度地图搜索页"

        # 提取地址
        for line in text.split("\n"):
            if "地址" in line or "位置" in line:
                import re as _re
                m = _re.search(r"地址[：:]\s*(.+)", line)
                if m:
                    result["address"] = m.group(1).strip()
                    break
            # 也提取公司名（搜索结果中第一个匹配的标题）
            if company[:2] in line and not result["name"] or result["name"] == company:
                if len(line) > 4 and len(line) < 100:
                    result["name"] = line.strip()

        if result["all_phones"]:
            print(f"    [OK] 百度地图: {result['name']} - {', '.join(result['all_phones'])}")
        else:
            print(f"    [-] 百度地图搜索页未发现电话")
            # 也试试搜索建议API作为补充
            try:
                api = ctx.request
                su_resp = api.get(f"{_BASE}/su?wd={wd}&cid=131&rn=5")
                raw = su_resp.text()
                if raw:
                    # 在建议数据中搜电话
                    all_phones2 = extractor.extract(raw)
                    for p in all_phones2:
                        if p not in result["all_phones"]:
                            result["all_phones"].append(p)
                    if result["all_phones"]:
                        result["source"] = "百度地图建议"
                        print(f"    [OK] 百度地图建议: {', '.join(result['all_phones'])}")
            except Exception:
                pass

        b.close()

    return result


if __name__ == "__main__":
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
