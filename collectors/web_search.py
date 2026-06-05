"""采集器: 网页搜索（步骤4）

使用 Bing / Baidu 搜索引擎 + 页面抓取，提取公司电话。
"""
from collectors.base import BaseCollector


class WebSearchCollector(BaseCollector):
    """通过搜索引擎（Bing / Baidu）搜索公司电话"""

    name = "网页搜索"
    confidence = "low"

    def collect(self, company: str, existing_phones: set = None) -> dict:
        """
        构造多个搜索 query，依次调用 Bing/Baidu，抓取结果页面提取电话。

        Args:
            company: 公司名称
            existing_phones: 已发现的电话集合（用于去重）

        Returns:
            {"phones": set, "sources": list, "log": str}
        """
        existing_phones = existing_phones or set()
        new_phones = set()
        sources = []
        log_lines = []

        queries = [
            f"{company} 联系电话",
            f"{company} 电话",
            f"{company} 联系方式",
        ]

        for q in queries[:1]:  # 目前只用第一个 query（与 lite_search.py 保持一致）
            log_lines.append(f'4/5 搜索: "{q}"')
            try:
                results = self._search(q, max_results=3)
                if not results:
                    log_lines.append("  ✗ 搜索引擎无结果")
                    continue

                from extractors.phone import PhoneExtractor
                extractor = PhoneExtractor(prefer_nearby=False)

                for r in results:
                    page_text = self._fetch_page(r["url"])
                    text = r.get("snippet", "") + " " + page_text
                    for p in extractor.extract(text):
                        if p not in existing_phones and p not in new_phones:
                            new_phones.add(p)
                            sources.append(
                                self._make_source(
                                    p,
                                    source=r["url"][:50],
                                    title=r.get("title", "")[:40],
                                )
                            )
                    if new_phones:
                        break  # 找到即停

                if new_phones:
                    log_lines.append(f"  ✓ 搜索找到电话: {' | '.join(new_phones)}")
                else:
                    log_lines.append("  ✗ 搜索未找到电话")

            except Exception as ex:
                log_lines.append(f"  ✗ 搜索异常: {str(ex)[:40]}")
                self.logger.debug(f"网页搜索异常: {ex}")

        return {
            "phones": new_phones,
            "sources": sources,
            "log": "\n".join(log_lines),
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _search(query: str, max_results: int = 3) -> list[dict]:
        """先 Bing 后 Baidu，返回搜索结果列表。"""
        try:
            from skills.engines import search_bing, search_baidu
        except ImportError:
            return []

        results = search_bing(query, max_results=max_results)
        if not results:
            results = search_baidu(query, max_results=max_results)
        return results

    @staticmethod
    def _fetch_page(url: str) -> str:
        """获取页面纯文本。"""
        try:
            from skills.engines import fetch_page_text
            return fetch_page_text(url)
        except ImportError:
            return ""
