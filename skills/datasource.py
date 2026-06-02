"""企业信息数据源查询 — 直接从百科/天眼查/企查查/百度地图获取"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from extractors.phone import PhoneExtractor
from urllib.parse import quote


def query_baidu_baike(company: str) -> str:
    """从百度百科获取公司页面文本"""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = ctx.new_page()
        # 先搜索百科，找到准确的条目
        url = f"https://baike.baidu.com/item/{quote(company)}"
        page.goto(url)
        page.wait_for_timeout(3000)
        text = page.content()
        b.close()
        return text


def query_company_source(company: str, source: str = "auto") -> list[str]:
    """
    从多个数据源查询公司联系方式。
    source: 'baike' | 'tianyancha' | 'qichacha' | 'aiqicha' | 'baidumap' | 'auto'
    """
    extractor = PhoneExtractor(prefer_nearby=True)
    all_phones = set()

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = ctx.new_page()

        sources_to_try = []
        if source == "auto":
            sources_to_try = ["aiqicha", "tianyancha", "qichacha", "baike", "baidumap"]
        else:
            sources_to_try = [source]

        for src in sources_to_try:
            try:
                if src == "baike":
                    url = f"https://baike.baidu.com/item/{quote(company)}"
                    label = "百度百科"
                elif src == "tianyancha":
                    url = f"https://www.tianyancha.com/search?key={quote(company)}"
                    label = "天眼查"
                elif src == "qichacha":
                    url = f"https://www.qichacha.com/search?key={quote(company)}"
                    label = "企查查"
                elif src == "aiqicha":
                    url = f"https://aiqicha.baidu.com/s?q={quote(company)}"
                    label = "爱企查"
                elif src == "baidumap":
                    url = f"https://map.baidu.com/search/{quote(company)}"
                    label = "百度地图"
                else:
                    continue

                print(f"  -> 查询{label}: {company}")
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_timeout(4000)

                # 检查是否被拦截
                if 'captcha' in page.url.lower() or '安全验证' in page.title():
                    print(f"  [!] {label} 触发验证码，跳过")
                    continue

                # 用 evaluate 取渲染后的文本（比 content() 更可靠）
                try:
                    text = page.evaluate('() => document.body.innerText')
                except Exception:
                    text = page.content()

                phones = extractor.extract(text)
                for p in phones:
                    all_phones.add(p)
                if phones:
                    print(f"  [OK] {label} 发现 {len(phones)} 个电话: {', '.join(phones)}")
                else:
                    print(f"  [-] {label} 未发现电话")
                time.sleep(1)

            except Exception as e:
                print(f"  [X] {label} 查询失败: {e}")

        b.close()

    return sorted(all_phones)


if __name__ == '__main__':
    import sys
    company = sys.argv[1] if len(sys.argv) > 1 else "山东金泉水处理有限公司"
    print(f"\n{'='*50}")
    print(f"[企业数据源查询] {company}")
    print(f"{'='*50}")
    phones = query_company_source(company, source="auto")
    print(f"\n{'='*50}")
    print(f"[结果] 共找到 {len(phones)} 个电话")
    for p in phones:
        print(f"  [电话] {p}")
