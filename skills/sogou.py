"""搜狗搜索技能 (Playwright)"""

import logging
from urllib.parse import quote, urljoin
from skills.base import SearchSkill

logger = logging.getLogger(__name__)


class SogouSearch(SearchSkill):
    """搜狗搜索引擎爬虫"""

    engine_name = "sogou"
    search_url = "https://www.sogou.com/web?query={query}&ie=utf8"

    def search(self, query: str, max_results: int = 50) -> list[dict]:
        self._ensure_browser()
        url = self.search_url.format(query=quote(query))
        logger.info(f"  -> 正在搜狗搜索: {query}")
        self.page.goto(url)
        self.page.wait_for_timeout(3000)

        results = []
        # 搜狗结果: h3 > a
        h3_a_list = self.page.locator('h3 a').all()
        for i, a in enumerate(h3_a_list[:max_results]):
            try:
                title = a.inner_text().strip()
                href = a.get_attribute('href') or ''
                if not title or not href:
                    continue
                # 补全相对路径为绝对 URL
                if href.startswith('/'):
                    href = urljoin('https://www.sogou.com', href)
                if href.startswith('http') and 'sogou.com' not in href:
                    results.append({
                        'title': title,
                        'url': href,
                        'snippet': '',
                        'index': i + 1,
                    })
            except Exception:
                continue

        # 兜底: 找 .vrwrap 或 .vr5-wrap 中的链接
        if not results:
            for cls in ['.vrwrap', '.vr5-wrap']:
                items = self.page.locator(cls).all()
                for i, item in enumerate(items[:max_results]):
                    try:
                        a = item.locator('a').first
                        if a.count() == 0:
                            continue
                        title = a.inner_text().strip()
                        href = a.get_attribute('href') or ''
                        if href.startswith('/'):
                            href = urljoin('https://www.sogou.com', href)
                        if title and href and href.startswith('http') and 'sogou.com' not in href:
                            results.append({
                                'title': title,
                                'url': href,
                                'snippet': '',
                                'index': i + 1,
                            })
                    except Exception:
                        continue
                if results:
                    break

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
