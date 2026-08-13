# -*- coding: utf-8 -*-
"""
基础爬虫类 (BaseScraper)

所有平台爬虫的抽象基类，提供统一的反检测、限速、重试与去重机制。
参考 https://github.com/MohsinCell/NLP-Review-Authenticity-Analysis 的反爬策略：
  - 随机 User-Agent 轮换池
  - 随机延迟抖动 (jitter)
  - 指数退避重试
  - robots.txt 合规检查
  - 评论去重 (ID + 文本指纹)

本模块使用 requests + BeautifulSoup 实现（已安装），不依赖 Playwright。
"""

import abc
import hashlib
import random
import re
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


# 用户代理轮换池：覆盖桌面端常见浏览器，降低被识别为爬虫的概率
USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
]

# 移动端 User-Agent 池：部分平台（淘宝等）移动端接口更易获取数据
MOBILE_USER_AGENT_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
]


class BaseScraper(abc.ABC):
    """平台爬虫抽象基类。

    子类必须实现 :meth:`parse_reviews`，并按需重写 :meth:`scrape`。
    """

    # 子类可覆盖：平台名称，用于结果标记与日志
    platform_name: str = "base"


    # ═══════════════════════════════════════════════════════════
    # 评论溯源字段（每条评论必须包含）
    # 严禁使用AI生成虚假评论，所有评论必须可溯源
    # ═══════════════════════════════════════════════════════════
    # source_platform: 来源平台 (taobao/jd)
    # source_url:      商品页面URL
    # product_id:      平台商品ID
    # reviewer_name:   评论者昵称
    # review_date:     评论日期
    # sku:             购买的SKU规格
    # ═══════════════════════════════════════════════════════════

    def __init__(self, delay: float = 2.0, timeout: int = 15, max_retries: int = 3):
        """初始化爬虫。

        :param delay: 请求之间的基础延迟秒数（实际会叠加随机抖动）
        :param timeout: 单次请求超时秒数
        :param max_retries: 请求失败最大重试次数（指数退避）
        """
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries

        # 复用 TCP 连接，提升性能并降低握手开销
        self.session = requests.Session()

        # 已抓取评论去重集合，键为评论指纹（review_id + 文本哈希）
        self._seen_keys: set = set()

        # Cookie 容器，子类可通过 set_cookies 注入登录态
        self._cookies: Dict[str, str] = {}

        # 是否遵守 robots.txt（生产环境建议开启）
        self.respect_robots = True
        self._robots_cache: Dict[str, set] = {}

    # ------------------------------------------------------------------
    # 反检测相关辅助方法
    # ------------------------------------------------------------------
    def _random_user_agent(self, mobile: bool = False) -> str:
        """从轮换池中随机选取一个 User-Agent。

        :param mobile: 是否使用移动端 UA（淘宝等推荐移动端）
        :return: 随机 User-Agent 字符串
        """
        pool = MOBILE_USER_AGENT_POOL if mobile else USER_AGENT_POOL
        return random.choice(pool)

    def _build_headers(self, url: str, mobile: bool = False, extra: Optional[Dict] = None) -> Dict[str, str]:
        """构建带反检测特征的请求头。

        :param url: 目标 URL，用于推断 Referer / Origin
        :param mobile: 是否伪装为移动端
        :param extra: 额外需要合并的请求头
        :return: 完整请求头字典
        """
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        headers = {
            "User-Agent": self._random_user_agent(mobile=mobile),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,application/json,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": origin + "/",
            "Origin": origin,
            # 模拟正常浏览器的 Sec-CH-UA 系列，降低指纹识别风险
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", '
                         '"Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?1" if mobile else "?0",
            "sec-ch-ua-platform": '"Android"' if mobile else '"Windows"',
        }
        if extra:
            headers.update(extra)
        return headers

    def _random_delay(self, base: Optional[float] = None) -> float:
        """计算带随机抖动的延迟时间。

        在基础延迟上叠加 [0, base) 的随机量，使请求间隔更接近人类行为。
        返回实际等待的秒数。
        """
        b = self.delay if base is None else base
        jitter = random.uniform(0, b * 0.8)
        wait = b + jitter
        time.sleep(wait)
        return wait

    # ------------------------------------------------------------------
    # robots.txt 合规检查
    # ------------------------------------------------------------------
    def _can_fetch(self, url: str) -> bool:
        """检查目标 URL 是否被 robots.txt 允许抓取。

        :param url: 目标 URL
        :return: 允许抓取返回 True
        """
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        try:
            if base not in self._robots_cache:
                robots_url = base + "/robots.txt"
                resp = self.session.get(robots_url, timeout=self.timeout)
                if resp.status_code == 200:
                    # 简易解析：记录 Disallow 路径
                    disallowed = set()
                    for line in resp.text.splitlines():
                        line = line.strip()
                        if line.lower().startswith("disallow:"):
                            path = line.split(":", 1)[1].strip()
                            if path:
                                disallowed.add(path)
                    self._robots_cache[base] = disallowed
                else:
                    # robots.txt 不存在，默认允许
                    self._robots_cache[base] = set()
            disallowed = self._robots_cache[base]
            for path in disallowed:
                if path == "/" or parsed.path.startswith(path):
                    return False
            return True
        except Exception:
            # robots.txt 检查失败时不阻断流程，保守起见允许抓取
            return True

    # ------------------------------------------------------------------
    # Cookie 管理（部分平台需要登录态）
    # ------------------------------------------------------------------
    def set_cookies(self, cookies: Dict[str, str]) -> None:
        """注入登录 Cookie。

        淘宝、京东等平台抓取评论通常需要登录态，可通过浏览器
        开发者工具复制 Cookie 后调用本方法注入。

        :param cookies: Cookie 字典，例如 {"cookie_name": "cookie_value"}
        """
        self._cookies.update(cookies)
        # 同步到 session，便于后续请求自动携带
        for name, value in cookies.items():
            self.session.cookies.set(name, value)

    # ------------------------------------------------------------------
    # 核心请求方法
    # ------------------------------------------------------------------
    def fetch_page(self, url: str, params: Optional[Dict] = None,
                   mobile: bool = False, extra_headers: Optional[Dict] = None,
                   method: str = "GET", data: Optional[Dict] = None) -> Optional[str]:
        """发起 HTTP 请求并返回响应文本。

        包含以下反检测与健壮性策略：
          - 随机 User-Agent 轮换
          - 随机延迟抖动
          - 指数退避重试
          - robots.txt 合规检查

        :param url: 目标 URL
        :param params: 查询参数
        :param mobile: 是否伪装移动端
        :param extra_headers: 额外请求头
        :param method: 请求方法 GET / POST
        :param data: POST 请求体
        :return: 响应文本；失败返回 None
        """
        # robots.txt 合规检查
        if not self._can_fetch(url):
            print(f"[{self.platform_name}] robots.txt 禁止抓取: {url}")
            return None

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                # 随机延迟，模拟人类操作间隔
                self._random_delay()

                headers = self._build_headers(url, mobile=mobile, extra=extra_headers)

                if method.upper() == "POST":
                    resp = self.session.post(
                        url, params=params, data=data, headers=headers,
                        timeout=self.timeout, cookies=self._cookies,
                    )
                else:
                    resp = self.session.get(
                        url, params=params, headers=headers,
                        timeout=self.timeout, cookies=self._cookies,
                    )

                # 触发反爬时常见状态码，进行退避重试
                if resp.status_code in (429, 503):
                    backoff = self.delay * (2 ** attempt)
                    print(f"[{self.platform_name}] 触发限流 "
                          f"(HTTP {resp.status_code})，{backoff:.1f}s 后重试 "
                          f"({attempt}/{self.max_retries})")
                    time.sleep(backoff)
                    continue

                resp.raise_for_status()
                # 部分接口返回 JSON，部分返回 HTML，统一返回文本
                return resp.text

            except requests.RequestException as e:
                last_error = e
                backoff = self.delay * (2 ** attempt)
                print(f"[{self.platform_name}] 请求失败 "
                      f"({attempt}/{self.max_retries}): {e}，"
                      f"{backoff:.1f}s 后重试")
                time.sleep(backoff)

        print(f"[{self.platform_name}] 抓取失败，已达最大重试次数: {url} "
              f"| 错误: {last_error}")
        return None

    # ------------------------------------------------------------------
    # 去重辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _fingerprint(review_id: str, text: str, rating: Optional[float] = None) -> str:
        """生成评论指纹，用于去重。

        采用 review_id + 文本前 150 字归一化 + 评分的组合指纹，
        参考 ReviewIQ 的去重策略。

        :param review_id: 评论唯一标识
        :param text: 评论正文
        :param rating: 评分
        :return: 指纹字符串
        """
        normalized = re.sub(r"\s+", "", text)[:150].lower()
        composite = f"{review_id}|{normalized}|{rating}"
        return hashlib.md5(composite.encode("utf-8")).hexdigest()

    def _dedupe(self, reviews: List[Dict]) -> List[Dict]:
        """对评论列表去重，返回未出现过的评论。

        :param reviews: 待去重的评论列表
        :return: 去重后的新评论列表
        """
        unique: List[Dict] = []
        for r in reviews:
            key = self._fingerprint(
                str(r.get("user_id", "")),
                r.get("review_text", ""),
                r.get("rating"),
            )
            if key in self._seen_keys:
                continue
            self._seen_keys.add(key)
            unique.append(r)
        return unique

    # ------------------------------------------------------------------
    # 抽象方法与主流程
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def parse_reviews(self, html: str, **kwargs) -> List[Dict]:
        """解析响应内容，提取评论数据。子类必须实现。

        :param html: 接口/页面返回的文本（可能是 JSON 或 HTML）
        :return: 评论字典列表
        """
        raise NotImplementedError

    def scrape(self, url: str, max_reviews: int = 100, **kwargs) -> List[Dict]:
        """主抓取流程：获取页面并解析评论，直到达到数量上限。

        子类可按需重写以支持分页（如京东多页评论）。

        :param url: 起始 URL
        :param max_reviews: 最多抓取评论数
        :return: 评论列表
        """
        text = self.fetch_page(url, **kwargs)
        if not text:
            return []
        reviews = self.parse_reviews(text)
        reviews = self._dedupe(reviews)
        # 截取到目标数量
        return reviews[:max_reviews]

    # ------------------------------------------------------------------
    # 生命周期管理
    # ------------------------------------------------------------------
    def close(self) -> None:
        """释放会话资源。"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
