"""百度搜索技能 (Playwright + DOM JavaScript) — 完善版"""

import time
from urllib.parse import quote
from skills.base import SearchSkill


class BaiduSearch(SearchSkill):
    """百度搜索引擎爬虫 — 支持多页翻页搜索"""

    engine_name = "baidu"
    search_url = "https://www.baidu.com/s?wd={query}&ie=utf-8&pn={pn}"

    # JS: 提取搜索结果（仅站外链接，排除百度导航）
    SEARCH_JS = """() => {
        const results = [];
        const seenTitles = new Set();
        const seenUrls = new Set();

        const BAIDU_DOMAINS = [
            'baidu.com/s?', 'baidu.com/from', 'baidu.com/gaoji',
            'news.baidu.com', 'tieba.baidu.com', 'zhidao.baidu.com',
            'wenku.baidu.com', 'image.baidu.com', 'video.baidu.com',
            'map.baidu.com', 'music.baidu.com', 'xueshu.baidu.com',
            'top.baidu.com', 'passport.baidu.com', 'hao123.com',
            'baijiahao.baidu.com', 'live.baidu.com',
        ];

        const isBaiduNav = (url) => {
            return BAIDU_DOMAINS.some(d => url.includes(d));
        };

        const allLinks = document.querySelectorAll('a[href]');
        const candidates = [];

        for (const a of allLinks) {
            const href = a.getAttribute('href') || '';
            const title = (a.textContent || '').trim();
            if (!title || !href.startsWith('http')) continue;
            if (isBaiduNav(href)) continue;
            candidates.push({a, href, title});
        }

        const h3Links = candidates.filter(c => c.a.closest('h3'));
        for (const c of h3Links) {
            if (seenTitles.has(c.title) || seenUrls.has(c.href)) continue;
            seenTitles.add(c.title);
            seenUrls.add(c.href);
            results.push({title: c.title, url: c.href, snippet: '', index: results.length + 1});
            if (results.length >= 15) break;
        }

        return results;
    }"""

    # JS: 检查安全验证
    CAPTCHA_CHECK_JS = """() => {
        const title = document.title || '';
        const bodyText = (document.body && document.body.textContent) || '';
        return title.includes('安全验证') || title.includes('百度验证') || 
               bodyText.includes('请完成安全验证') || 
               document.querySelector('#captcha, .captcha, .passMod_puzzle') !== null;
    }"""

    # JS: 获取下一页URL
    NEXT_PAGE_JS = """() => {
        const next = document.querySelector('a.n');
        if (!next) return null;
        let h = next.getAttribute('href');
        if (h && h.startsWith('/')) h = 'https://www.baidu.com' + h;
        return h;
    }"""

    # JS: 模拟滚动
    SIMULATE_SCROLL_JS = """() => {
        window.scrollTo(0, 300);
        setTimeout(() => { window.scrollTo(0, 800); }, 800);
        setTimeout(() => { window.scrollTo(0, 1500); }, 1500);
        setTimeout(() => { window.scrollTo(0, 0); }, 2200);
    }"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._search_page_html = ''
        self._search_page_url = ''
        self._last_query = ''

    def search(self, query: str, max_results: int = 50) -> list[dict]:
        self._ensure_browser()
        self._last_query = query

        all_results = []
        seen_urls = set()
        page_num = 0

        max_pages = (max_results + 9) // 10 if max_results > 0 else 5
        max_pages = min(max_pages, 5)

        print(f"  -> 正在百度搜索: {query}  (最多 {max_results} 条/{max_pages} 页)")

        # 先用 desktop 版搜索
        desktop_ok = True
        while page_num < max_pages and len(all_results) < max_results:
            # ===== 翻页 =====
            if page_num == 0:
                url = self.search_url.format(query=quote(query), pn=0)
                if not self._load_page_safe(url):
                    desktop_ok = False
                    break
                # 额外等待 AI 摘要/企业信息卡片加载（百度动态渲染）
                try:
                    self.page.wait_for_timeout(5000)
                except Exception:
                    pass
            else:
                # 模拟阅读
                self._simulate_reading()
                # 尝试点击下一页
                if not self._go_next_page():
                    pn = page_num * 10
                    if not self._load_page_safe(
                        self.search_url.format(query=quote(query), pn=pn)
                    ):
                        break

            # ===== 检测验证码 =====
            if self._check_captcha():
                if self._recover_from_captcha(page_num):
                    print(f"  [OK] 验证解除")
                else:
                    print(f"  [X] 第{page_num+1}页验证无法跳过，停止翻页")
                    desktop_ok = False
                    break

            # ===== 提取本页结果 =====
            page_results = self.page.evaluate(self.SEARCH_JS)

            for r in page_results:
                if r['url'] not in seen_urls:
                    seen_urls.add(r['url'])
                    r['page'] = page_num + 1
                    all_results.append(r)

            # 保存第1页HTML（含AI摘要）
            if page_num == 0:
                try:
                    self._search_page_html = self.page.content()
                    self._search_page_url = self.page.url
                except Exception:
                    pass

            page_count = len(page_results)
            print(f"  第{page_num+1}页: {page_count} 条 (累计 {len(all_results)}/{max_results})")
            page_num += 1

        print(f"  [OK] 共获取 {len(all_results)} 条 (来自 {page_num} 页)")

        # 用手机版百度搜索补充获取 AI 摘要中的电话
        # （桌面版 headless 浏览器经常拿不到百度企业信息卡片）
        try:
            mobile_phones = self._mobile_search_supplement(query)
            if mobile_phones:
                print(f"  [手机版] AI摘要补充: {', '.join(mobile_phones)}")
                # 追加到搜索页文本中，方便 main.py 提取
                self._search_page_html = (self._search_page_html or '') + '\n' + '\n'.join(mobile_phones)
        except Exception as e:
            print(f"  [!] 手机版搜索失败: {e}")

        return all_results[:max_results]

    def _mobile_search_supplement(self, query: str) -> list[str]:
        """用手机版百度搜索补充获取企业信息"""
        from utils.helpers import extract_phone_numbers
        old_ctx = self._context
        old_page = self._page

        # 新建手机版上下文
        from skills.base import _stealth, HAS_STEALTH
        mobile_ctx = self._browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            locale="zh-CN",
        )
        mobile_page = mobile_ctx.new_page()
        if HAS_STEALTH:
            try:
                _stealth.apply_stealth_sync(mobile_page)
            except Exception:
                pass
        mobile_page.goto(f"https://m.baidu.com/s?word={quote(query)}")
        mobile_page.wait_for_timeout(5000)

        text = mobile_page.evaluate("() => document.body.innerText")
        mobile_ctx.close()

        # 恢复原页面
        self._context = old_ctx
        self._page = old_page

        from extractors.phone import PhoneExtractor
        pe = PhoneExtractor(prefer_nearby=True)
        return pe.extract(text)

    def open_result(self, url: str) -> str:
        self._ensure_browser()
        self.page.goto(url)
        self.page.wait_for_timeout(2000)
        try:
            return self.page.content()
        except Exception:
            return ''

    def _load_page_safe(self, url: str) -> bool:
        """安全加载页面"""
        try:
            self.page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
            self.page.wait_for_timeout(3000)
            return True
        except Exception as e:
            err = str(e)[:80].encode('gbk', errors='replace').decode('gbk')
            print(f"  [!] 页面加载异常: {err}")
            return False

    def _check_captcha(self) -> bool:
        """检查是否触发验证码，返回 True 表示有验证码"""
        try:
            return self.page.evaluate(self.CAPTCHA_CHECK_JS)
        except Exception:
            return ('captcha' in self.page.url or '安全验证' in self.page.title())

    def _recover_from_captcha(self, page_num: int) -> bool:
        """多策略尝试解除验证码"""
        for attempt in range(3):
            if attempt == 0:
                print(f"  [!] 刷新页面...")
                try:
                    self.page.reload()
                    self.page.wait_for_timeout(3000)
                except Exception:
                    pass
            elif attempt == 1:
                pn = page_num * 10
                url = self.search_url.format(query=quote(self._last_query), pn=pn)
                print(f"  [!] JS跳转重试...")
                try:
                    self.page.evaluate(f"window.location.href='{url}'")
                    self.page.wait_for_timeout(5000)
                except Exception:
                    pass
            else:
                print(f"  [!] 等待10秒后最后尝试...")
                time.sleep(10)
                try:
                    self.page.reload()
                    self.page.wait_for_timeout(3000)
                except Exception:
                    pass

            if not self._check_captcha():
                return True

        # === 终极手段：新建浏览器上下文直接打开目标页 ===
        # （复用已有浏览器实例开新 context，避免 Playwright 嵌套限制）
        print(f"  [!] 尝试新浏览器上下文直接打开第{page_num+1}页...")
        try:
            pn = page_num * 10
            target_url = self.search_url.format(
                query=quote(self._last_query), pn=pn
            )

            fresh_ctx = self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
            )
            fresh_page = fresh_ctx.new_page()
            fresh_page.goto(target_url, timeout=self.timeout)
            fresh_page.wait_for_timeout(3000)

            # 检查是否有验证码
            has_captcha = False
            try:
                has_captcha = fresh_page.evaluate(self.CAPTCHA_CHECK_JS)
            except Exception:
                has_captcha = 'captcha' in fresh_page.url.lower()

            if not has_captcha:
                print(f"  [OK] 新上下文成功加载第{page_num+1}页！")
                # 关闭旧页面，替换为新的
                self._page.close()
                self._page = fresh_page
                self._context = fresh_ctx
                return True

            fresh_ctx.close()
        except Exception as fresh_e:
            print(f"  [!] 新上下文也失败: {fresh_e}")

        return False

    def _simulate_reading(self):
        """模拟阅读行为"""
        try:
            for y in [300, 800, 1500, 500, 0]:
                self.page.evaluate(f"window.scrollTo(0, {y})")
                time.sleep(0.6)
        except Exception:
            pass
        time.sleep(1.0)

    def _go_next_page(self) -> bool:
        """点击下一页按钮"""
        try:
            next_url = self.page.evaluate(self.NEXT_PAGE_JS)
            if not next_url:
                print(f"  [!] 没有下一页")
                return False

            print(f"  -> 翻到下一页...")
            # 方法1: 点击按钮
            try:
                btn = self.page.locator('a.n')
                if btn.count() > 0:
                    btn.first.click()
                    self.page.wait_for_timeout(3000)
                    return True
            except Exception:
                pass

            # 方法2: JS 导航
            self.page.evaluate(f"window.location.href='{next_url}'")
            self.page.wait_for_timeout(4000)
            return True
        except Exception as e:
            print(f"  [!] 翻页失败: {e}")
            return False
