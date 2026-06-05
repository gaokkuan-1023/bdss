"""采集器: AI 搜索验证（步骤5）

调用 skills.ai.AISearch，从 AI 返回的摘要中提取电话。
无论前面步骤是否已找到电话，均执行此步骤。
"""
from collectors.base import BaseCollector


class AIVerifyCollector(BaseCollector):
    """调用 AI 搜索引擎验证 / 补充公司电话"""

    name = "AI搜索"
    confidence = "medium"

    def collect(self, company: str, existing_phones: set = None) -> dict:
        """
        调用 AISearch 查询公司，从返回的 snippet 中提取电话。

        Args:
            company: 公司名称
            existing_phones: 已发现的电话集合（用于去重）

        Returns:
            {"phones": set, "sources": list, "log": str}
        """
        existing_phones = existing_phones or set()
        new_phones = set()
        sources = []
        log_lines = [f"5/5 AI搜索: {company}"]

        try:
            from skills.ai import AISearch
            from extractors.phone import PhoneExtractor

            ai = AISearch()
            results = ai.search(company, max_results=3)

            extractor = PhoneExtractor(prefer_nearby=False)
            for r in results:
                snippet = r.get("snippet", "")
                if not snippet:
                    continue
                for p in extractor.extract(snippet):
                    if p not in existing_phones and p not in new_phones:
                        new_phones.add(p)
                        sources.append(
                            self._make_source(
                                p,
                                source="AI搜索",
                                title=r.get("title", ""),
                            )
                        )

            if new_phones:
                log_lines.append("  ok AI找到: " + " | ".join(new_phones))
            else:
                log_lines.append("  ✗ AI搜索未找到电话")

        except ImportError:
            log_lines.append("  ✗ AI搜索模块不可用，跳过")
            self.logger.debug("skills.ai 模块导入失败")
        except Exception as ex:
            log_lines.append(f"  ✗ AI搜索失败: {str(ex)[:40]}")
            self.logger.debug(f"AI搜索异常: {ex}")

        return {
            "phones": new_phones,
            "sources": sources,
            "log": "\n".join(log_lines),
        }
