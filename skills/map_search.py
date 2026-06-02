"""百度地图 POI 查询 — 搜索公司名称获取地址和电话"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from extractors.phone import PhoneExtractor
from urllib.parse import quote


def baidu_map_search(company: str) -> list[str]:
    """从百度地图搜索公司，提取 POI 详情中的电话"""
    extractor = PhoneExtractor(prefer_nearby=True)
    phones = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.set_default_timeout(30000)

        # 用手机版百度地图（更轻量，适合 headless）
        url = f"https://map.baidu.com/?newmap=1&s=s%26wd%3D{quote(company)}%26c%3D1&from=alamap&tp=detail"
        print(f"  [百度地图] 搜索: {company}")
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
        except Exception as e:
            print(f"  [!] 页面加载: {type(e).__name__}")
        page.wait_for_timeout(5000)
        print(f"  当前URL: {page.url}")
        print(f"  标题: {page.title()}")

        text = page.evaluate("() => document.body.innerText")
        print(f"  页面文本长度: {len(text)}")
        # 输出前500字看看内容
        print(f"  页面内容开头: {text[:500]}")

        found = extractor.extract(text)
        for p in found:
            phones.add(p)
        if found:
            print(f"  [OK] 发现 {len(found)} 个电话: {', '.join(found)}")
        else:
            print(f"  [-] 未发现电话")

        browser.close()

    return sorted(phones)


if __name__ == '__main__':
    company = sys.argv[1] if len(sys.argv) > 1 else "山东金泉水处理有限公司"
    print(f"\n{'='*50}")
    print(f"[百度地图 POI 查询] {company}")
    print(f"{'='*50}")
    phones = baidu_map_search(company)
    print(f"\n{'='*50}")
    print(f"[结果] 共找到 {len(phones)} 个电话")
    for p in phones:
        print(f"  [电话] {p}")
