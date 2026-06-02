"""手机版百度搜索 + 百度地图 POI 查询"""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from extractors.phone import PhoneExtractor
from urllib.parse import quote


def mobile_baidu_search(company: str) -> list[str]:
    """用手机版百度搜索，获取企业信息"""
    extractor = PhoneExtractor(prefer_nearby=True)
    phones = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.goto(f"https://m.baidu.com/s?word={quote(company)}")
        page.wait_for_timeout(5000)

        # 获取渲染文本
        text = page.evaluate("() => document.body.innerText")
        print(f"  [手机百度] 页面文本长度: {len(text)}")

        found = extractor.extract(text)
        for p in found:
            phones.add(p)
        if found:
            print(f"  [手机百度] 发现 {len(found)} 个: {', '.join(found)}")

        browser.close()

    return sorted(phones)


def baidu_map_poi(company: str) -> list[str]:
    """从百度地图 POI 获取公司电话"""
    extractor = PhoneExtractor(prefer_nearby=True)
    phones = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        url = f"https://map.baidu.com/search/{quote(company)}"
        print(f"  [百度地图] 搜索: {company}")
        page.goto(url)
        page.wait_for_timeout(6000)

        # 获取文本
        text = page.evaluate("() => document.body.innerText")
        print(f"  [百度地图] 页面文本长度: {len(text)}")

        found = extractor.extract(text)
        for p in found:
            phones.add(p)
        if found:
            print(f"  [百度地图] 发现 {len(found)} 个: {', '.join(found)}")

        browser.close()

    return sorted(phones)


if __name__ == '__main__':
    company = sys.argv[1] if len(sys.argv) > 1 else "山东金泉水处理有限公司"
    print(f"\n{'='*50}")
    print(f"[查询] {company}")
    print(f"{'='*50}")

    mobile = mobile_baidu_search(company)
    print(f"\n[手机百度结果] {len(mobile)} 个电话: {', '.join(mobile) if mobile else '无'}")

    map_poi = baidu_map_poi(company)
    print(f"\n[百度地图结果] {len(map_poi)} 个电话: {', '.join(map_poi) if map_poi else '无'}")
