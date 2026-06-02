"""Bing 搜索技能 (Playwright)"""

from urllib.parse import quote
from skills.base import SearchSkill


class BingSearch(SearchSkill):
    """必应搜索引擎爬虫"""

    engine_name = "bing"
    search_url = "https://cn.bing.com/search?q={query}&ensearch=0"

    def search(self, query: str, max_results: int = 50) -> list[dict]:
        self._ensure_browser()
        url = self.search_url.format(query=quote(query))
        print(f"  -> 正在必应搜索: {query}")
        self.page.goto(url)
        self.page.wait_for_timeout(3000)

        results = []
        # 必应搜索结果的几种可能结构
        items = self.page.locator('li.b_algo').all()
        if items:
            for i, item in enumerate(items[:max_results]):
                try:
                    a = item.locator('h2 a').first
                    if a.count() == 0:
                        continue
                    title = a.inner_text().strip()
                    href = a.get_attribute('href') or ''
                    snippet = ''
                    cap = item.locator('.b_caption p').first
                    if cap.count() > 0:
                        snippet = cap.inner_text().strip()
                    if title and href:
                        results.append({
                            'title': title,
                            'url': href,
                            'snippet': snippet,
                            'index': i + 1,
                        })
                except Exception:
                    continue
        else:
            # 兜底: 所有 h2 > a
            all_h2_a = self.page.locator('h2 a').all()
            for i, a in enumerate(all_h2_a[:max_results]):
                try:
                    title = a.inner_text().strip()
                    href = a.get_attribute('href') or ''
                    if title and href and not href.startswith('javascript'):
                        results.append({
                            'title': title,
                            'url': href,
                            'snippet': '',
                            'index': i + 1,
                        })
                except Exception:
                    continue

        print(f"  [OK] 获取到 {len(results)} 条搜索结果")
        return results

    def open_result(self, url: str) -> str:
        self._ensure_browser()
        self.page.goto(url)
        self.page.wait_for_timeout(2000)
        try:
            return self.page.content()
        except Exception:
            return ''
