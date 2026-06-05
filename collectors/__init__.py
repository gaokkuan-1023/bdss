"""轻量搜索采集器集合 — 每步一个独立采集器"""

from collectors.bidding_db import BiddingDBCollector
from collectors.baidu_poi import BaiduPOICollector
from collectors.huangye import HuangyeCollector
from collectors.web_search import WebSearchCollector
from collectors.ai_verify import AIVerifyCollector

# 采集器注册表 — 按优先级排序
COLLECTORS = [
    BiddingDBCollector,
    BaiduPOICollector,
    HuangyeCollector,
    WebSearchCollector,
    AIVerifyCollector,
]

__all__ = [
    "BiddingDBCollector",
    "BaiduPOICollector",
    "HuangyeCollector",
    "WebSearchCollector",
    "AIVerifyCollector",
    "COLLECTORS",
]
