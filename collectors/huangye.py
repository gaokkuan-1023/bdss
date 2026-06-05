"""采集器: 顺企网查询（步骤3）

从 11467.com（顺企网）搜索公司电话。
"""
import urllib.parse
import urllib.request

from collectors.base import BaseCollector


class HuangyeCollector(BaseCollector):
    """从顺企网（11467.com）搜索公司电话"""

    name = "顺企网"
    confidence = "medium"

    # 请求头
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    }

    def collect(self, company: str, existing_phones: set = None) -> dict:
        """
        请求顺企网搜索页面，从 HTML 中提取电话。

        Args:
            company: 公司名称
            existing_phones: 已发现的电话集合（用于去重）

        Returns:
            {"phones": set, "sources": list, "log": str}
        """
        existing_phones = existing_phones or set()
        new_phones = set()
        sources = []
        log_lines = ["3/5 顺企网查询中..."]

        try:
            from extractors.phone import PhoneExtractor

            key = urllib.parse.quote(company[:6])
            url = f"https://www.11467.com/company/search.php?key={key}"

            req = urllib.request.Request(url, headers=self._HEADERS)
            resp = urllib.request.urlopen(req, timeout=8)
            html = resp.read().decode("utf-8", errors="replace")

            extractor = PhoneExtractor(prefer_nearby=False)
            for p in extractor.extract(html):
                if p not in existing_phones and p not in new_phones:
                    new_phones.add(p)
                    sources.append(self._make_source(p, source="顺企网", title=""))

            if new_phones:
                log_lines.append(f"  ✓ 顺企网找到电话: {' | '.join(new_phones)}")
            else:
                log_lines.append("  ✗ 顺企网未找到电话")

        except Exception as ex:
            log_lines.append(f"  ✗ 顺企网查询失败: {str(ex)[:40]}")
            self.logger.debug(f"顺企网查询失败: {ex}")

        return {
            "phones": new_phones,
            "sources": sources,
            "log": "\n".join(log_lines),
        }
