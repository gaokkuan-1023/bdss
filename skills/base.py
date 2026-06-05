"""搜索引擎抽象基类 — 统一接口协议"""
import logging
from abc import ABC, abstractmethod
from typing import Optional


logger = logging.getLogger(__name__)


class BaseEngine(ABC):
    """
    所有搜索引擎的抽象基类。
    
    子类必须实现:
      - search(company, max_results) -> list[dict]
      - open_result(result) -> dict
    
    可选覆盖:
      - search_and_open(company, max_results) -> dict  (默认组合 search + open_result)
      - close()  (默认空操作)
      - available -> bool  (默认 True)
    """
    
    def __init__(self, headless: bool = True, proxy: Optional[str] = None, **kwargs):
        self.headless = headless
        self.proxy = proxy
        self._logger = logging.getLogger(self.__class__.__module__)
    
    @property
    def available(self) -> bool:
        """引擎是否可用（如需要 API Key 但没配置时返回 False）"""
        return True
    
    @abstractmethod
    def search(self, company: str, max_results: int = 5) -> list:
        """
        搜索公司，返回结果列表。
        每个结果至少包含: {"title": str, "url": str, "snippet": str}
        """
        ...
    
    @abstractmethod
    def open_result(self, result: dict) -> dict:
        """
        打开单个搜索结果，提取详细信息。
        返回: {"page_text": str, "phones": list[str], ...}
        """
        ...
    
    def search_and_open(self, company: str, max_results: int = 5) -> tuple:
        """
        搜索并打开前 N 个结果 — 一站式接口。
        返回: (opened_pages: list[dict], search_page_text: str|None)
        
        默认实现: search() → 逐个 open_result()
        子类可覆盖以提供更高效的实现。
        """
        from extractors.phone import PhoneExtractor
        extractor = PhoneExtractor(prefer_nearby=True)
        
        results = self.search(company, max_results=max_results)
        opened = []
        search_text = ""
        
        for r in results:
            try:
                detail = self.open_result(r)
                detail.update({
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                })
                opened.append(detail)
                if detail.get("page_text"):
                    search_text += " " + detail["page_text"]
            except Exception as e:
                self._logger.debug(f"open_result 失败: {r.get('url', '?')[:50]} → {e}")
        
        return opened, search_text
    
    def close(self):
        """释放资源（浏览器、连接等），默认空操作"""
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
