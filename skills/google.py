"""Google 搜索技能 (Playwright)"""

from urllib.parse import quote, urlparse, parse_qs
import logging
from skills.base import SearchSkill

logger = logging.getLogger(__name__)


class GoogleSearch(SearchSkill):
    """Google 搜索引擎爬虫"""

    engine_name = "google"
    search_url = "https://www.google.com/search?q={query}&hl=zh-CN"

    @staticmethod
    def _extract_real_url(google_url: str) -> str:
        """从 Google 跳转链接中提取真实 URL"""
        if '/url?q=' in google_url or 'google.com/url?' in google_url:
            parsed = urlparse(google_url)
            params = parse_qs(parsed.query)
            return params.get('q', [google_url])[0]
        return google_url

    def search(self, query: str, max_results: int = 50) -> list[dict]:
        self._ensure_browser()
        url = self.search_url.format(query=quote(query))
        logger.info(f"  -> 正在 Google 搜索: {query}")
        self.page.goto(url)
        self.page.wait_for_timeout(3000)

        results = []
        # Google 结果在 div.g 中
        items = self.page.locator('div.g').all()
        if not items:
            items = self.page.locator('h3').all()

        for i, item in enumerate(items[:max_results]):
            try:
                a = item.locator('a').first
                if a.count() == 0:
                    continue
                title = a.inner_text().strip()
                href = a.get_attribute('href') or ''
                real_url = self._extract_real_url(href)
                if title and real_url and 'google.com' not in real_url:
                    results.append({
                        'title': title,
                        'url': real_url,
                        'snippet': '',
                        'index': i + 1,
                    })
            except Exception:
                continue

        logger.info(f"  [OK] 获取到 {len(results)} 条搜索结果")
        return results

    def open_result(self, url: str) -> str:
        self._ensure_browser()
        self.page.goto(url)
        self.page.wait_for_timeout(2000)
        try:
            return self.page.content()
        except Exception:
            return ''
