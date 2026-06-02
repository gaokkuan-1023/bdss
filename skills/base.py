"""搜索引擎技能基类 - 统一使用 Playwright 引擎"""

from abc import ABC, abstractmethod
from typing import Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
try:
    from playwright_stealth import Stealth
    _stealth = Stealth()
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False


class SearchSkill(ABC):
    """搜索引擎技能基类 (Playwright 引擎)"""

    engine_name = "base"

    def __init__(self, headless: bool = True, proxy: Optional[str] = None,
                 timeout: float = 120):
        self.headless = headless
        self.proxy = proxy
        self.timeout = timeout * 1000  # Playwright uses ms
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._started = False

    def _ensure_browser(self):
        """确保浏览器已启动"""
        if not self._started:
            pw = sync_playwright()
            p = pw.start()
            launch_kwargs = {"headless": self.headless}
            if self.proxy:
                launch_kwargs["proxy"] = {"server": self.proxy}

            self._browser = p.chromium.launch(**launch_kwargs)
            self._context = self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            self._page = self._context.new_page()
            # 注入反检测 stealth（隐藏自动化痕迹）
            if HAS_STEALTH:
                try:
                    _stealth.apply_stealth_sync(self._page)
                except Exception:
                    pass
            # 设置页面加载超时（毫秒）
            self._page.set_default_timeout(self.timeout)
            self._pw = p
            self._started = True

    @property
    def page(self) -> Page:
        """获取当前页面"""
        self._ensure_browser()
        return self._page

    @abstractmethod
    def search(self, query: str, max_results: int = 50) -> list[dict]:
        """
        在搜索引擎中搜索关键词，返回搜索结果列表。

        Args:
            query: 搜索关键词
            max_results: 最多返回结果数（默认 50，-1 表示不限）
        """
        ...

    @abstractmethod
    def open_result(self, url: str) -> str:
        """
        打开搜索结果页面，返回页面文本。
        """
        ...

    def search_and_open(self, query: str, max_results: int = 5) -> list[dict]:
        """搜索并打开前 N 个结果"""
        results = self.search(query, max_results=50)  # 搜尽量多的结果
        opened = []

        # 获取搜索结果页面的渲染文本（比 page.content() 更完整，含 JS 动态内容）
        search_page_text = ''
        try:
            # 用 evaluate 获取渲染后的全部文本
            search_page_text = self.page.evaluate('() => document.body.innerText')
        except Exception:
            try:
                search_page_text = self.page.content()
            except Exception:
                pass

        # 合并手机版补充搜索的电话（如果有的话）
        if hasattr(self, '_search_page_html') and self._search_page_html:
            if not search_page_text:
                search_page_text = self._search_page_html
            else:
                search_page_text = search_page_text + '\n' + self._search_page_html[-2000:]

        for i, r in enumerate(results[:max_results]):
            try:
                text = self.open_result(r['url'])
                opened.append({**r, 'page_text': text})
                title_str = str(r.get('title', '') or '')[:40]
                title_safe = title_str.encode('gbk', errors='replace').decode('gbk')
                print(f"  [OK] 已打开: {title_safe}...")
            except Exception as e:
                err_msg = str(e).encode('gbk', errors='replace').decode('gbk') if isinstance(e, UnicodeEncodeError) else str(e)
                title_str = str(r.get('title', '') or '')[:30]
                title_safe = title_str.encode('gbk', errors='replace').decode('gbk')
                print(f"  [X] 打开失败: {title_safe} - {err_msg[:60]}")
                opened.append({**r, 'page_text': ''})

        return opened, search_page_text

    def close(self):
        """关闭浏览器"""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if hasattr(self, '_pw') and self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._context = None
        self._page = None
        self._started = False
