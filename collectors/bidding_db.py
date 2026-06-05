"""采集器: 招标数据库查询（步骤0）

从 bidding_monitor.db 中已有的招标线索电话。
"""
from collectors.base import BaseCollector


class BiddingDBCollector(BaseCollector):
    """查询招标数据库缓存中的电话"""

    name = "招标数据库"
    confidence = "high"

    def collect(self, company: str, existing_phones: set = None) -> dict:
        """
        从 bidding_monitor.db 中搜索匹配该公司的招标记录，提取电话。

        Args:
            company: 公司名称
            existing_phones: 已发现的电话集合（用于去重）

        Returns:
            {"phones": set, "sources": list, "log": str}
        """
        existing_phones = existing_phones or set()
        new_phones = set()
        sources = []
        log_lines = [f"0/5 招标数据库查询: {company}"]

        try:
            from bidding_monitor import get_db, close_db
            from extractors.phone import PhoneExtractor

            extractor = PhoneExtractor(prefer_nearby=False)
            conn = get_db()
            rows = conn.execute(
                "SELECT phone FROM bidding_items "
                "WHERE (buyer LIKE ? OR title LIKE ?) AND phone != '' "
                "ORDER BY matched_at DESC LIMIT 5",
                (f"%{company}%", f"%{company}%"),
            ).fetchall()

            if rows:
                for row in rows:
                    for p in extractor.extract(row[0]):
                        if p not in existing_phones and p not in new_phones:
                            new_phones.add(p)
                            sources.append(self._make_source(p, source="招标数据库", title=""))
                if new_phones:
                    log_lines.append(f"  ✓ 招标数据库找到电话: {' | '.join(new_phones)}")
                else:
                    log_lines.append("  - 招标数据库电话均已重复，跳过")
            else:
                log_lines.append("  - 招标数据库未找到")

        except ImportError:
            log_lines.append("  - 招标数据库模块不可用，跳过")
            self.logger.debug("bidding_monitor 模块导入失败")
        except Exception as ex:
            log_lines.append("  - 招标数据库查询 skipped")
            self.logger.debug(f"招标数据库查询异常: {ex}")

        return {
            "phones": new_phones,
            "sources": sources,
            "log": "\n".join(log_lines),
        }
