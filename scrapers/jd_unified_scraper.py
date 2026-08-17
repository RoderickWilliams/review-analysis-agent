"""
京东评论统一抓取器 — 三级降级调度
==================================
按反爬能力从强到弱依次尝试，任一方式抓到评论即返回：

  Level 1  DrissionPage 真实 Chrome + 手动登录 + DOM 虚拟滚动
           （来自 JD_Spider, https://github.com/LacYCle/JD_Spider）
  Level 2  Patchright / Playwright 反检测浏览器 + API 拦截 + DOM
           （已有 jd_playwright_scraper.py）
  Level 3  requests 直连 club.jd.com JSONP API
           （来自 JDComment_Spider, https://github.com/YuleZhang/JDComment_Spider
            和 rupu-product-analysis, https://github.com/jameszhi2/rupu-product-analysis）

任意一级失败或返回空，自动降级到下一级。
最后仍无评论时，收集所有浏览器方式产生的截图，交由上层 ScreenshotAnalyzer OCR。

接口：
  scraper = JDUnifiedScraper(max_reviews=50)
  reviews = scraper.scrape(url, cookies=...)
  screenshots = scraper.get_screenshots()
"""

import os
from typing import Dict, List, Optional


class JDUnifiedScraper:
    """统一调度多种京东抓取方式，自动降级。"""

    def __init__(
        self,
        max_reviews: int = 50,
        headless: bool = False,
        methods: Optional[List[str]] = None,
        login_timeout: int = 180,
    ):
        """
        :param max_reviews: 最多采集条数（各级共享上限）
        :param headless: 无头模式（DrissionPage/Playwright 共用，默认 False 以便扫码登录）
        :param methods: 指定使用的方法列表，按优先级排序；
                        默认 ['drissionpage', 'playwright', 'api']
        :param login_timeout: DrissionPage 等待登录超时秒数
        """
        self.max_reviews = max_reviews
        self.headless = headless
        self.methods = methods or ["drissionpage", "playwright", "api"]
        self.login_timeout = login_timeout
        self._screenshots: List[str] = []
        self._last_method: Optional[str] = None
        self._method_results: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # 各级抓取器（懒加载）
    # ------------------------------------------------------------------

    def _scrape_drissionpage(self, url: str, cookies: Optional[Dict]) -> List[Dict]:
        from scrapers.jd_drissionpage_scraper import JDDrissionPageScraper
        scraper = JDDrissionPageScraper(
            max_reviews=self.max_reviews,
            headless=self.headless,
            login_timeout=self.login_timeout,
        )
        try:
            reviews = scraper.scrape(url, cookies=cookies, max_reviews=self.max_reviews)
            self._screenshots.extend(scraper.get_screenshots())
            return reviews
        finally:
            # DrissionPage 浏览器保持打开给用户看，不强制关闭
            pass

    def _scrape_playwright(self, url: str, cookies: Optional[Dict]) -> List[Dict]:
        from scrapers.jd_playwright_scraper import JDPlaywrightScraper
        scraper = JDPlaywrightScraper(
            headless=self.headless,
            max_reviews=self.max_reviews,
        )
        try:
            reviews = scraper.scrape(url, cookies=cookies, max_reviews=self.max_reviews)
            self._screenshots.extend(scraper.get_screenshots())
            return reviews
        finally:
            try:
                scraper._close_browser()
            except Exception:
                pass

    def _scrape_api(self, url: str, cookies: Optional[Dict]) -> List[Dict]:
        from scrapers.jd_api_scraper import JDAPIScraper
        scraper = JDAPIScraper(max_reviews=self.max_reviews, cookies=cookies)
        try:
            return scraper.scrape(url, max_reviews=self.max_reviews)
        finally:
            scraper.close()

    # ------------------------------------------------------------------
    # 主调度
    # ------------------------------------------------------------------

    def scrape(self, product_url: str, cookies: Optional[Dict] = None,
               max_reviews: Optional[int] = None) -> List[Dict]:
        if max_reviews is not None:
            self.max_reviews = max_reviews

        self._screenshots = []
        self._last_method = None
        self._method_results = {}

        method_map = {
            "drissionpage": self._scrape_drissionpage,
            "playwright": self._scrape_playwright,
            "api": self._scrape_api,
        }

        for method in self.methods:
            handler = method_map.get(method)
            if not handler:
                self._method_results[method] = "未知方法，跳过"
                continue

            print("[jd-unified] 尝试方式: %s" % method)
            try:
                reviews = handler(product_url, cookies)
                if reviews:
                    self._last_method = method
                    self._method_results[method] = "成功 %d 条" % len(reviews)
                    print("[jd-unified] ✅ %s 成功，采集 %d 条" % (method, len(reviews)))
                    return reviews
                else:
                    self._method_results[method] = "返回 0 条"
                    print("[jd-unified] ⚠ %s 返回 0 条，降级" % method)
            except Exception as e:
                self._method_results[method] = "异常: %s" % e
                print("[jd-unified] ❌ %s 异常: %s，降级" % (method, e))
                import traceback
                traceback.print_exc()

        print("[jd-unified] 所有方式均失败，共收集 %d 张截图可供 OCR" % len(self._screenshots))
        return []

    def get_screenshots(self) -> List[str]:
        """返回所有方式产生的截图路径（已过滤不存在的）。"""
        return [s for s in self._screenshots if os.path.exists(s)]

    @property
    def last_method(self) -> Optional[str]:
        """最后成功的方法名。"""
        return self._last_method

    @property
    def method_results(self) -> Dict[str, str]:
        """各方法的执行结果摘要。"""
        return dict(self._method_results)

    def close(self):
        """统一清理（目前 DrissionPage 浏览器由 GC 处理，预留接口）。"""
        pass


def scrape_jd_reviews_unified(url: str, max_reviews: int = 50,
                              cookies: Optional[Dict] = None,
                              methods: Optional[List[str]] = None) -> List[Dict]:
    """便捷函数。"""
    s = JDUnifiedScraper(max_reviews=max_reviews, methods=methods)
    return s.scrape(url, cookies=cookies)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python jd_unified_scraper.py <京东商品URL> [最大评论数] [方法1,方法2,...]")
        sys.exit(1)
    test_url = sys.argv[1]
    test_max = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    test_methods = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    scraper = JDUnifiedScraper(max_reviews=test_max, methods=test_methods)
    result = scraper.scrape(test_url)
    print("\n===== 采集结果（%d 条，方法: %s）=====" % (len(result), scraper.last_method))
    for i, r in enumerate(result, 1):
        print("[%d] %d星 | %s | %s" % (
            i, r.get("rating", 0), r.get("reviewer_name", ""),
            r.get("review_text", "")[:80],
        ))
