"""采集器基类"""
import logging
from typing import Optional


class BaseCollector:
    """
    轻量搜索采集器基类。

    每个采集器实现一个独立的数据获取步骤。
    """

    name: str = "base"
    confidence: str = "low"  # high / medium / low

    def __init__(self):
        self.logger = logging.getLogger(f"collector.{self.name}")

    def collect(self, company: str, existing_phones: set = None) -> dict:
        """
        执行采集。

        Args:
            company: 公司名称
            existing_phones: 已发现的电话集合（用于去重）

        Returns:
            {
                "phones": set[str],       # 新发现的电话
                "sources": list[dict],     # 来源记录
                "log": str,               # 步骤日志
            }
        """
        raise NotImplementedError

    def _make_source(self, phone: str, source: str = "", title: str = "") -> dict:
        """构造标准来源记录"""
        return {
            "phone": phone,
            "source": source or self.name,
            "title": title,
            "confidence": self.confidence,
        }
