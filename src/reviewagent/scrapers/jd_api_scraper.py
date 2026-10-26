"""
京东评论抓取器 — 纯 API 直连版（最轻量降级方案）
=================================================
直接请求 club.jd.com 的评论 JSONP 接口。

参考来源：
  - JDComment_Spider (https://github.com/YuleZhang/JDComment_Spider)
  - rupu-product-analysis (https://github.com/jameszhi2/rupu-product-analysis)

原理：
  京东商品评论的官方接口是：
    https://club.jd.com/comment/productPageComments.action
      ?callback=fetchJSON_comment98
      &productId={sku}
      &score=0            # 0全部 1差评 2中评 3好评
      &sortType=5         # 5推荐排序 6时间排序
      &page=0             # 从 0 开始
      &pageSize=10
      &isShadowSku=0
      &fold=1
  返回 JSONP，剥掉 callback(...) 外壳后是 JSON。

注意：
  - 该接口在未登录或无 Cookie 时极可能返回空 comments 或 403
  - 仅作为降级链路的最后一级；有真实 Cookie（来自浏览器持久化 profile）时成功率显著提升
  - 加入随机 UA、Referer、随机延迟、重试退避
"""

import json
import random
import re
import time
from typing import Dict, List, Optional

import requests

# 禁用 SSL 警告（京东证书链在某些环境下会报错）
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

# 可选：fake-useragent 提供更真实的随机 UA
try:
    from fake_useragent import UserAgent
    _FAKE_UA = UserAgent()
except Exception:
    _FAKE_UA = None


USER_AGENTS = [
    # 桌面端 Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    # 移动端 UA（JRAS 项目使用，部分接口对移动端反爬更宽松）
    "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
]

COMMENT_API = "https://club.jd.com/comment/productPageComments.action"
PRODUCT_PAGE_API = "https://item.jd.com/{sku}.html"

# 京东商品评论接口的 score 参数
SCORE_ALL = 0      # 全部评论（JDComment_Spider 使用）
SCORE_ALL_ALT = 4  # 全部评论（JRAS 项目使用，实际接口兼容值）
SORT_RECOMMEND = 5

# 请求变体：不同 callback / score / UA 组合，轮流尝试以提高成功率
# 来自三个参考项目的不同实践：
#   - JDComment_Spider: callback=fetchJSON_comment98 + score=0
#   - rupu-product-analysis: callback=fetchJSON_comment{rand} + score=0
#   - JRAS: 无 callback（直接返回 JSON）+ score=4
REQUEST_VARIANTS = [
    {"use_callback": True, "score": SCORE_ALL, "mobile": False},
    {"use_callback": False, "score": SCORE_ALL_ALT, "mobile": True},
    {"use_callback": True, "score": SCORE_ALL_ALT, "mobile": False},
    {"use_callback": False, "score": SCORE_ALL, "mobile": True},
]


class JDAPIScraper:
    """通过京东评论 JSONP 接口直连抓取评论。"""

    def __init__(
        self,
        max_reviews: int = 50,
        cookies: Optional[Dict[str, str]] = None,
        cookie_str: Optional[str] = None,
        timeout: int = 15,
        max_retries: int = 3,
        delay_range: tuple = (1.5, 3.5),
        traverse_sorting: bool = True,
    ):
        """
        :param max_reviews: 最多采集条数
        :param cookies: dict 形式的 cookie（如 {'pt_key': '...', 'pt_pin': '...'}）
        :param cookie_str: 原始 Cookie 头字符串，优先级高于 cookies dict
        :param timeout: 请求超时秒数
        :param max_retries: 单页最大重试次数
        :param delay_range: 每页之间随机延迟区间（秒）
        :param traverse_sorting: 是否遍历京东评论筛选方式（score=0~5，跳过 6）。
               京东对每种筛选方式最多返回约 100 页，开启遍历可绕开此上限采集更多数据。
               参考 XiaoBai-Data/JD-Comment-Crawler 项目。
        """
        self.max_reviews = max_reviews
        self.timeout = timeout
        self.max_retries = max_retries
        self.delay_range = delay_range
        self.traverse_sorting = traverse_sorting
        self._product_name = ""

        self.session = requests.Session()
        self.session.verify = False
        # 绕过系统代理，防止代理篡改响应编码或跳转港澳版
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}

        if cookie_str:
            self.session.headers["Cookie"] = cookie_str
        elif cookies:
            self.session.headers["Cookie"] = "; ".join(
                f"{k}={v}" for k, v in cookies.items()
            )

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_product_id(url: str) -> str:
        # 港澳版 jd.hk
        m = re.search(r"jd\.hk/[^\d]*(\d{5,})", url)
        if m:
            return m.group(1)
        m = re.search(r"item\.jd\.com/(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"productId=(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"/(\d{5,})\.html", url)
        if m:
            return m.group(1)
        m = re.search(r"(\d{6,})", url)
        if m:
            return m.group(1)
        return ""

    @staticmethod
    def _parse_jsonp(text: str) -> Optional[Dict]:
        """剥掉 fetchJSON_commentXX(...) 外壳，返回 dict。"""
        if not text:
            return None
        # 找第一个 { 和最后一个 }
        s = text.find("{")
        e = text.rfind("}")
        if s < 0 or e <= s:
            return None
        try:
            return json.loads(text[s:e + 1])
        except json.JSONDecodeError:
            # 兜底：正则
            m = re.search(r"fetchJSON_comment\d*\((.*)\)\s*;?\s*$", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    return None
        return None

    def _random_ua(self, mobile: bool = False) -> str:
        """优先使用 fake-useragent（真实浏览器指纹），失败回退到内置列表。"""
        if _FAKE_UA is not None:
            try:
                # fake-useragent 支持按 platform/min_version 等过滤
                if mobile:
                    ua = _FAKE_UA.random
                    # 简单判断：包含 Mobile/Android/iPhone 才返回
                    if any(k in ua for k in ("Mobile", "Android", "iPhone")):
                        return ua
                else:
                    ua = _FAKE_UA.random
                    if "Mobile" not in ua and "Android" not in ua:
                        return ua
            except Exception:
                pass
        # 回退内置池
        pool = USER_AGENTS
        if mobile:
            pool = [u for u in USER_AGENTS if "Mobile" in u or "Android" in u or "iPhone" in u] or USER_AGENTS
        return random.choice(pool)

    def _build_headers(self, product_id: str, mobile: bool = False) -> Dict:
        ua = self._random_ua(mobile=mobile)
        return {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": f"https://item.jd.com/{product_id}.html",
            "Host": "club.jd.com",
            "Sec-Fetch-Dest": "script",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-site",
            "Connection": "keep-alive",
        }

    def _fetch_page(self, product_id: str, page: int,
                    variant: Optional[Dict] = None) -> Optional[Dict]:
        """
        请求单页评论。按 variant 指定的参数组合尝试；
        如果 variant 为 None，则按 REQUEST_VARIANTS 顺序自动轮询直到拿到数据。
        """
        if variant is None:
            for v in REQUEST_VARIANTS:
                result = self._fetch_page(product_id, page, variant=v)
                if result and (result.get("comments") or result.get("productCommentSummary")):
                    return result
                # 短暂等待避免切太快
                time.sleep(0.5)
            return None

        use_callback = variant.get("use_callback", True)
        score = variant.get("score", SCORE_ALL)
        mobile = variant.get("mobile", False)

        params = {
            "productId": product_id,
            "score": score,
            "sortType": SORT_RECOMMEND,
            "page": page,
            "pageSize": 10,
            "isShadowSku": 0,
            "fold": 1,
        }
        if use_callback:
            params["callback"] = f"fetchJSON_comment{random.randint(90, 9999)}"

        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(
                    COMMENT_API,
                    params=params,
                    headers=self._build_headers(product_id, mobile=mobile),
                    timeout=self.timeout,
                )
                if resp.status_code == 403:
                    print("[jd-api] 403 风控（variant=%s, 第%d次）" % (variant, attempt + 1))
                    time.sleep(2 + attempt * 2)
                    continue
                if resp.status_code != 200:
                    print("[jd-api] HTTP %d（variant=%s, 第%d次）" % (resp.status_code, variant, attempt + 1))
                    time.sleep(1 + attempt)
                    continue

                text = resp.text.strip()
                # JRAS 风格：无 callback，直接 json.loads
                if not use_callback:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        pass  # 可能仍是 JSONP，走下面 parse
                data = self._parse_jsonp(text)
                if data is not None:
                    return data
                print("[jd-api] 响应解析失败（variant=%s, 第%d次）" % (variant, attempt + 1))
            except requests.RequestException as e:
                print("[jd-api] 请求异常: %s（第%d次）" % (e, attempt + 1))
            time.sleep(1 + attempt)

        return None

    def _fetch_product_name(self, product_id: str) -> str:
        """尝试从商品页抓取商品名称（优先 title 标签，最可靠）。"""
        try:
            resp = self.session.get(
                PRODUCT_PAGE_API.format(sku=product_id),
                headers={
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                # 修复编码（京东返回的页面可能被误判为 ISO-8859-1）
                if resp.apparent_encoding and resp.encoding != resp.apparent_encoding:
                    resp.encoding = resp.apparent_encoding
                # 方式1：从 <title> 标签提取（最可靠）
                m = re.search(r"<title>(.*?)</title>", resp.text, re.DOTALL)
                if m:
                    title = m.group(1).strip()
                    # 京东 title 格式：商品名【图片 价格 品牌 报价】-京东
                    name = title.split("-京东")[0].split("-")[0].split("·")[0].strip()
                    name = re.sub(r'【.*?】.*$', '', name).strip()
                    if name and len(name) >= 2:
                        return name
                # 方式2：从 sku-name 提取（兜底）
                m = re.search(
                    r'<div\s+class="sku-name"[^>]*>(.*?)</div>',
                    resp.text, re.DOTALL,
                )
                if m:
                    name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                    if name and len(name) >= 2:
                        return name
        except Exception as e:
            print("[jd-api] 获取商品名称失败: %s" % e)
        return ""

    # ------------------------------------------------------------------
    # 评论格式化
    # ------------------------------------------------------------------

    def _format_review(self, raw: Dict, product_id: str, product_url: str) -> Optional[Dict]:
        content = (raw.get("content") or "").strip()
        if not content or len(content) < 3:
            return None

        nickname = str(raw.get("nickname") or "匿名用户")
        score = raw.get("score") or 5
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 5

        creation_time = str(raw.get("creationTime") or "")
        sku_parts = [
            str(raw.get("productColor") or ""),
            str(raw.get("productSize") or ""),
        ]
        sku = " ".join(p for p in sku_parts if p).strip()

        reference_name = raw.get("referenceName") or self._product_name
        comment_id = str(raw.get("id") or "")

        return {
            "review_text": self._clean_text(content),
            "rating": score,
            "platform": "jd",
            "timestamp": creation_time,
            "user_id": nickname,
            "product_name": reference_name,
            "source_platform": "jd",
            "source_url": product_url,
            "product_id": product_id,
            "review_permalink": f"{product_url}#comment-{comment_id}" if comment_id else f"{product_url}#comment",
            "reviewer_name": nickname,
            "reviewer_id": str(raw.get("uid") or raw.get("id") or ""),
            "review_date": creation_time,
            "sku": sku,
            "is_demo": False,
            "extraction_method": "requests_jsonp_api",
        }

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", str(text))
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def scrape(self, product_url: str, cookies: Optional[Dict] = None,
               max_reviews: Optional[int] = None) -> List[Dict]:
        """
        抓取京东商品评论（API 直连版）。

        :param product_url: 商品 URL 或纯 productId
        :param cookies: 可选，dict 形式 cookie
        :param max_reviews: 覆盖实例 max_reviews
        """
        if max_reviews is not None:
            self.max_reviews = max_reviews

        # 如果传入的是纯数字，当作 productId
        if product_url.isdigit():
            product_id = product_url
            product_url = f"https://item.jd.com/{product_id}.html"
        else:
            product_id = self._extract_product_id(product_url)

        if not product_id:
            print("[jd-api] 无法从 URL 提取商品 ID: %s" % product_url)
            return []

        # 运行时注入 cookies
        if cookies:
            self.session.headers["Cookie"] = "; ".join(
                f"{k}={v}" for k, v in cookies.items()
            )

        # 尝试拿商品名（失败不影响主流程）
        self._product_name = self._fetch_product_name(product_id)

        reviews: List[Dict] = []
        seen_ids = set()

        # 京东评论筛选方式 score 参数：
        #   0=全部, 1=差评, 2=中评, 3=好评, 4=全部(追评/视频混合), 5=晒图
        # XiaoBai-Data 项目遍历 0~5（跳过 6），可采集更多数据
        if self.traverse_sorting:
            score_modes = [0, 1, 2, 3, 4, 5]
        else:
            score_modes = [0]

        for score_mode in score_modes:
            if len(reviews) >= self.max_reviews:
                break
            page = 0
            empty_pages = 0
            print("[jd-api] 开始 score=%d 筛选方式" % score_mode)

            while len(reviews) < self.max_reviews and page < 10000:
                # 按当前 score 构造 variant
                variant = {
                    "use_callback": True,
                    "score": score_mode,
                    "mobile": False,
                }
                data = self._fetch_page(product_id, page=page, variant=variant)
                if data is None:
                    print("[jd-api] score=%d 第 %d 页请求失败" % (score_mode, page))
                    break

                comments = data.get("comments") or []
                if not comments:
                    empty_pages += 1
                    if empty_pages >= 2:
                        break
                    page += 1
                    continue
                empty_pages = 0

                new_count = 0
                for c in comments:
                    cid = str(c.get("id") or "")
                    if cid and cid in seen_ids:
                        continue
                    if cid:
                        seen_ids.add(cid)
                    review = self._format_review(c, product_id, product_url)
                    if review:
                        reviews.append(review)
                        new_count += 1
                        if len(reviews) >= self.max_reviews:
                            break

                print("[jd-api] score=%d 第 %d 页：%d 条（累计 %d）" % (
                    score_mode, page, new_count, len(reviews)))

                page += 1
                time.sleep(random.uniform(*self.delay_range))

        print("[jd-api] 采集完成，共 %d 条" % len(reviews))
        return reviews

    def get_screenshots(self) -> List[str]:
        """API 模式无截图，返回空列表以兼容统一接口。"""
        return []

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass


def scrape_jd_reviews_api(url: str, max_reviews: int = 50,
                          cookies: Optional[Dict] = None,
                          cookie_str: Optional[str] = None) -> List[Dict]:
    """便捷函数。"""
    s = JDAPIScraper(max_reviews=max_reviews, cookies=cookies, cookie_str=cookie_str)
    try:
        return s.scrape(url)
    finally:
        s.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python jd_api_scraper.py <京东商品URL或productId> [最大评论数]")
        sys.exit(1)
    test_url = sys.argv[1]
    test_max = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    result = scrape_jd_reviews_api(test_url, max_reviews=test_max)
    print("\n===== 采集结果（%d 条）=====" % len(result))
    for i, r in enumerate(result, 1):
        print("[%d] %d星 | %s | %s" % (
            i, r.get("rating", 0), r.get("reviewer_name", ""),
            r.get("review_text", "")[:80],
        ))
