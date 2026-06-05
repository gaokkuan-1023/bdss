"""搜索服务层 — 解耦 API 服务与 CLI 入口"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def search_company(
    company_name: str,
    engine: str = "ai",
    max_results: int = 5,
    headless: bool = True,
    proxy: Optional[str] = None,
    verbose: bool = False,
    delay: int = 0,
) -> dict:
    """
    搜索公司电话 — service 层入口。
    延迟导入 main.py，避免 API 服务启动时触发 CLI 模块的副作用。
    """
    from main import search_company as _search
    return _search(
        company_name=company_name,
        engine=engine,
        max_results=max_results,
        headless=headless,
        proxy=proxy,
        verbose=verbose,
        delay=delay,
    )


def search_all_engines(
    company_name: str,
    max_results: int = 5,
    headless: bool = True,
    proxy: Optional[str] = None,
    verbose: bool = False,
    delay: int = 0,
) -> dict:
    """多引擎合并搜索 — service 层入口"""
    from main import search_all_engines as _search_all
    return _search_all(
        company_name=company_name,
        max_results=max_results,
        headless=headless,
        proxy=proxy,
        verbose=verbose,
        delay=delay,
    )


def search_company_phones(company: str, log_detail: bool = False) -> dict:
    """轻量搜索 — service 层入口"""
    from skills.lite_search import search_company_phones as _lite
    return _lite(company, log_detail=log_detail)
