"""搜索引擎技能基类 - 统一使用 Playwright 引擎"""

from abc import ABC, abstractmethod
import logging
from typing import Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
try:
    from playwright_stealth import Stealth
    _stealth = Stealth()
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
logger = logging.getLogger(__name__)

# 默认 UA / Viewport（各引擎共享）
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}


class SearchSkill(ABC):
    """搜索引擎技能基类 (Playwright 引擎)"""

    engine_name = "base"

    def __init__(self, headless: bool = True, proxy: Optional[str] = None,
                 timeout: float = 120, shared_browser: Optional[Browser] = None,
                 shared_pw=None):
        self.headless = headless
        self.proxy = proxy
        self.timeout = timeout * 1000  # Playwright uses ms
        self._browser = shared_browser
        self._pw = shared_pw
        self._owns_browser = shared_browser is None  # 自己启动的才负责关闭
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._started = False

    def _ensure_browser(self):
        """确保浏览器已启动"""
        if not self._started:
            # === 自己启动浏览器（无共享实例时）===
            if self._owns_browser:
                pw = sync_playwright()
                p = pw.start()
                self._pw = p
                launch_kwargs = {"headless": self.headless}
                if self.proxy:
                    launch_kwargs["proxy"] = {"server": self.proxy}
                try:
                    # 优先使用系统 Chrome（避免重新下载 Chromium）
                    try:
                        self._browser = p.chromium.launch(**launch_kwargs, channel='chrome')
                    except Exception:
                        self._browser = p.chromium.launch(**launch_kwargs)
                except Exception as e:
                    err = str(e)
                    logger.error(f"Playwright 浏览器启动失败: {err}")
                    if "Executable doesn't exist" in err or "cannot find" in err:
                        print("\n⚠️  Playwright Chromium 未安装！请运行:")
                        print("   python -m playwright install chromium")
                        print()
                    raise
            # === 从共享浏览器创建 context + page ===
            self._context = self._browser.new_context(
                user_agent=_DEFAULT_UA,
                viewport=_DEFAULT_VIEWPORT,
                locale="zh-CN",
            )
            self._page = self._context.new_page()
            if HAS_STEALTH:
                try:
                    _stealth.apply_stealth_sync(self._page)
                except Exception as _e:
                    logger.debug(f"stealth 注入失败: {_e}")
            self._page.set_default_timeout(self.timeout)
            self._started = True

    @property
    def page(self) -> Page:
        """获取当前页面"""
        self._ensure_browser()
        return self._page

    @abstractmethod
    def search(self, query: str, max_results: int = 50) -> list[dict]:
        ...

    @abstractmethod
    def open_result(self, url: str) -> str:
        ...

    def search_and_open(self, query: str, max_results: int = 5) -> list[dict]:
        """搜索并打开前 N 个结果"""
        results = self.search(query, max_results=50)
        opened = []

        search_page_text = ''
        try:
            search_page_text = self.page.evaluate('() => document.body.innerText')
        except Exception:
            try:
                search_page_text = self.page.content()
            except Exception as _ex:
                logger.debug(f"忽略: {_ex}")

        if hasattr(self, '_search_page_html') and self._search_page_html:
            if not search_page_text:
                search_page_text = self._search_page_html
            else:
                extra = self._search_page_html.strip()
                if len(extra) > 3000:
                    extra = extra[-3000:]
                search_page_text = search_page_text + '\n' + extra

        for i, r in enumerate(results[:max_results]):
            try:
                text = self.open_result(r['url'])
                opened.append({**r, 'page_text': text})
                logger.info(f"  [OK] 已打开: {str(r.get('title', '') or '')[:40]}...")
            except Exception as e:
                logger.info(f"  [X] 打开失败: {str(r.get('title', '') or '')[:30]} - {str(e)[:60]}")
                opened.append({**r, 'page_text': ''})

        return opened, search_page_text

    def close(self):
        """关闭浏览器（仅自己启动的才关闭）"""
        if self._owns_browser:
            try:
                if self._context:
                    self._context.close()
                if self._browser and self._owns_browser:
                    self._browser.close()
                if self._pw:
                    self._pw.stop()
            except Exception as _ex:
                logger.debug(f"忽略: {_ex}")
        else:
            # 共享浏览器：只关闭 context+page，不关 browser
            try:
                if self._context:
                    self._context.close()
            except Exception as _ex:
                logger.debug(f"忽略: {_ex}")
            try:
                if self._page:
                    self._page.close()
            except Exception as _ex:
                logger.debug(f"忽略: {_ex}")
        self._context = None
        self._page = None
        # 不重置 _browser / _pw（共享实例不归我们管）
        self._started = False
