
# ═══════════════════════════════════════════════════════════════
# 伦理准则：严禁使用AI生成虚假评论进行虚假分析！
# 所有评论必须来自淘宝/天猫真实页面抓取
# 每条评论必须包含溯源字段（source_url, product_id, reviewer_name等）
# 爬取失败时如实告知，不得用虚假数据替代
# ═══════════════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
"""
淘宝 / 天猫商品评论爬虫 (TaobaoScraper)

负责解析淘宝、天猫商品的评价数据。

重要说明：
  淘宝/天猫的评论接口 (mtop) 需要登录态 Cookie 以及 sign 签名参数，
  签名由前端 JS 生成，纯 requests 难以直接复现。本爬虫提供：
    1. 商品 URL 解析（提取 item_id）
    2. 移动端评论接口请求结构
    3. 评论 JSON 解析逻辑
    4. Cookie 注入接口（需用户从浏览器复制登录 Cookie）
    5. HTML 回退解析（兜底方案）

  生产环境中建议配合 Playwright 获取 sign，或使用浏览器扩展注入 Cookie。
"""

import json
import re
import time
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


class TaobaoScraper(BaseScraper):
    """淘宝 / 天猫商品评论爬虫。"""

    platform_name = "taobao"

    # 移动端评论接口（mtop），需要 token + sign
    RATE_API = (
        "https://h5api.m.taobao.com/h5/mtop.taobao.rate.detaillist.get/6.0/"
    )
    # 商品详情页（用于 HTML 回退与商品名提取）
    ITEM_URL_TEMPLATES = {
        "taobao": "https://item.taobao.com/item.htm?id={item_id}",
        "tmall": "https://detail.tmall.com/item.htm?id={item_id}",
        "mobile": "https://a.m.taobao.com/i{item_id}.htm",
    }

    def __init__(self, delay: float = 2.0, timeout: int = 15, max_retries: int = 3):
        super().__init__(delay=delay, timeout=timeout, max_retries=max_retries)
        self.item_id: Optional[str] = None
        self.product_name: Optional[str] = None

    # ------------------------------------------------------------------
    # URL 解析
    # ------------------------------------------------------------------
    @staticmethod
    def parse_item_id(url: str) -> Optional[str]:
        """从淘宝/天猫商品 URL 中提取商品 ID (item_id)。

        支持的 URL 形式：
          - https://item.taobao.com/item.htm?id=123456
          - https://detail.tmall.com/item.htm?id=123456
          - https://a.m.taobao.com/i123456.htm
          - https://m.tb.cn/h.abc123 (短链需先跳转，本方法不处理短链)

        :param url: 商品 URL
        :return: item_id 字符串，解析失败返回 None
        """
        # 形如 ?id=123456 的查询参数
        match = re.search(r"[?&]id=(\d+)", url)
        if match:
            return match.group(1)
        # 形如 /i123456.htm 的移动端短路径
        match = re.search(r"/i(\d+)\.htm", url)
        if match:
            return match.group(1)
        # 形如 item.htm?spm=...&id=123456 已被第一规则覆盖
        return None

    # ------------------------------------------------------------------
    # Cookie 设置（覆盖基类以附加说明）
    # ------------------------------------------------------------------
    def set_cookies(self, cookies: Dict[str, str]) -> None:
        """注入淘宝登录 Cookie。

        淘宝评论接口必须携带登录态，所需关键字段通常包括：
          - _m_h5_tk: mtop 签名令牌（用于生成 sign）
          - _m_h5_tk_enc: mtop 加密令牌
          - cookie2 / sgcookie / t / unb 等登录凭证

        获取方式：浏览器登录淘宝后，F12 -> Application -> Cookies，
        复制对应字段调用本方法注入。

        :param cookies: Cookie 字典
        """
        super().set_cookies(cookies)
        # 校验是否包含 mtop 签名所需的关键 Cookie
        required = ["_m_h5_tk", "_m_h5_tk_enc"]
        missing = [k for k in required if k not in self._cookies]
        if missing:
            print(f"[taobao] 警告：缺少 mtop 签名所需 Cookie: {missing}，"
                  f"评论接口可能无法返回数据。请从浏览器复制完整登录 Cookie。")

    # ------------------------------------------------------------------
    # 签名生成（说明）
    # ------------------------------------------------------------------
    def _build_sign_token(self) -> Dict[str, str]:
        """从 _m_h5_tk Cookie 中提取 token，用于拼装 mtop 请求参数。

        mtop 的 sign 算法为：
          sign = md5(token + '&' + t + '&' + appKey + '&' + data)
        其中 token 取自 _m_h5_tk 的第一段（下划线前部分）。
        完整 sign 需要在前端 JS 环境执行，本方法仅提取 token 供参考。

        :return: 包含 token 与时间戳的字典
        """
        tk = self._cookies.get("_m_h5_tk", "")
        token = tk.split("_")[0] if tk else ""
        t = str(int(time.time() * 1000))
        return {"token": token, "t": t}

    def _build_rate_api_params(self, page: int = 1, page_size: int = 20,
                               sort: int = 0) -> Dict:
        """构建评论接口请求参数。

        :param page: 页码（从 1 开始）
        :param page_size: 每页条数
        :param sort: 排序方式 0=默认 1=有图 2=追加评价
        :return: 参数字典
        """
        token_info = self._build_sign_token()
        data = json.dumps({
            "auctionNumId": self.item_id,
            "currentPageNum": page,
            "pageSize": page_size,
            "rateType": "",
            "orderType": sort,
        }, ensure_ascii=False)
        params = {
            "jsv": "2.7.2",
            "appKey": "12574478",  # 移动端 H5 固定 appKey
            "t": token_info["t"],
            # 注意：sign 需在前端生成，这里留空，实际请求需自行注入
            "sign": "",
            "api": "mtop.taobao.rate.detaillist.get",
            "v": "6.0",
            "type": "originaljson",
            "dataType": "json",
            "data": data,
        }
        return params

    # ------------------------------------------------------------------
    # 商品名提取
    # ------------------------------------------------------------------
    def _fetch_product_name(self) -> str:
        """从商品详情页提取商品名称（用于结果聚合）。"""
        if not self.item_id:
            return ""
        url = self.ITEM_URL_TEMPLATES["mobile"].format(item_id=self.item_id)
        text = self.fetch_page(url, mobile=True)
        if not text:
            return ""
        soup = BeautifulSoup(text, "html.parser")
        # 标题标签优先级
        for selector in ["title", "meta[property='og:title']"]:
            tag = soup.select_one(selector)
            if tag:
                content = tag.get("content") or tag.get_text(strip=True)
                if content:
                    return content.split("-淘宝")[0].split("-天猫")[0].strip()
        return ""

    # ------------------------------------------------------------------
    # 评论解析
    # ------------------------------------------------------------------
    def parse_reviews(self, html: str, **kwargs) -> List[Dict]:
        """解析淘宝评论接口返回内容。

        接口返回 JSONP / JSON，结构为：
          { "data": { "rateList": [ { "feedback": ..., "rateScore": ... } ] } }

        若返回的是 HTML 页面（未带登录态时的登录跳转页），
        则尝试从页面中抽取内嵌的 JSON 数据。

        :param html: 接口或页面文本
        :return: 评论字典列表
        """
        reviews: List[Dict] = []
        if not html:
            return reviews

        data = self._extract_json(html)
        if data is None:
            # HTML 回退：尝试解析页面内嵌评价数据
            reviews = self._parse_html_reviews(html)
        else:
            reviews = self._parse_api_reviews(data)

        # 去重并补全 platform / product_name
        for r in reviews:
            r.setdefault("platform", self.platform_name)
            r.setdefault("product_name", self.product_name or "")
        return reviews

    def _extract_json(self, text: str) -> Optional[Dict]:
        """从响应文本中提取 JSON 对象（兼容 JSONP 包裹）。"""
        text = text.strip()
        # 去除 JSONP 回调包裹：mtopjsonp1({...})
        jsonp_match = re.match(r"^[a-zA-Z0-9_]+\((.*)\);?$", text, re.DOTALL)
        if jsonp_match:
            text = jsonp_match.group(1)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

    def _parse_api_reviews(self, data: Dict) -> List[Dict]:
        """解析 mtop 评论接口的标准 JSON 结构。"""
        reviews: List[Dict] = []
        rate_list = (
            data.get("data", {})
            .get("rateList", [])
            if isinstance(data, dict)
            else []
        )
        for item in rate_list:
            review = {
                "review_text": (item.get("feedback") or item.get("content") or "").strip(),
                "rating": self._parse_rating(item.get("rateScore")),
                "timestamp": self._parse_timestamp(item.get("rateDate") or item.get("gmtCreate")),
                "user_id": str(item.get("userNick") or item.get("displayUserNick") or
                               item.get("userId") or ""),
                "platform": self.platform_name,
                "product_name": self.product_name or "",
            }
            if review["review_text"]:
                reviews.append(review)
        return reviews

    def _parse_html_reviews(self, html: str) -> List[Dict]:
        """HTML 兜底解析：从详情页内嵌脚本中抽取评价 JSON。"""
        reviews: List[Dict] = []
        soup = BeautifulSoup(html, "html.parser")
        # 部分页面将评价数据内嵌在 <script> 标签中
        for script in soup.find_all("script"):
            text = script.string or script.get_text()
            if not text or "rateList" not in text:
                continue
            match = re.search(r"\"rateList\"\s*:\s*(\[.*?\])", text, re.DOTALL)
            if match:
                try:
                    rate_list = json.loads(match.group(1))
                    reviews.extend(self._parse_api_reviews({"data": {"rateList": rate_list}}))
                except (json.JSONDecodeError, ValueError):
                    continue
        return reviews

    @staticmethod
    def _parse_rating(score) -> Optional[float]:
        """将评分统一为浮点数。"""
        try:
            return float(score)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_timestamp(raw) -> str:
        """标准化时间戳，兼容毫秒/秒级数字与字符串日期。"""
        if not raw:
            return ""
        if isinstance(raw, (int, float)):
            # 毫秒级时间戳
            if raw > 1e12:
                return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(raw / 1000))
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(raw))
        return str(raw)

    # ------------------------------------------------------------------
    # 主抓取流程（支持分页）
    # ------------------------------------------------------------------
    def scrape(self, url: str, max_reviews: int = 100, **kwargs) -> List[Dict]:
        """抓取淘宝商品评论。

        :param url: 商品 URL 或直接传入 item_id
        :param max_reviews: 最大评论数
        :return: 评论列表
        """
        # 兼容直接传入 item_id
        if url.isdigit():
            self.item_id = url
        else:
            self.item_id = self.parse_item_id(url)

        if not self.item_id:
            print(f"[taobao] 无法从 URL 解析 item_id: {url}")
            return []

        # 提取商品名（可选，失败不影响评论抓取）
        try:
            self.product_name = self._fetch_product_name()
        except Exception as e:
            print(f"[taobao] 商品名提取失败: {e}")

        # 检查登录态
        if not self._cookies:
            print("[taobao] 警告：未设置登录 Cookie，评论接口大概率无法返回数据。"
                  "请通过 set_cookies() 注入浏览器登录 Cookie。")

        all_reviews: List[Dict] = []
        page = 1
        page_size = 20
        max_pages = (max_reviews // page_size) + 2

        while len(all_reviews) < max_reviews and page <= max_pages:
            params = self._build_rate_api_params(page=page, page_size=page_size)
            text = self.fetch_page(
                self.RATE_API, params=params, mobile=True,
                extra_headers={"Referer": self.ITEM_URL_TEMPLATES["mobile"].format(
                    item_id=self.item_id)},
            )
            if not text:
                break

            page_reviews = self.parse_reviews(text)
            page_reviews = self._dedupe(page_reviews)
            if not page_reviews:
                print(f"[taobao] 第 {page} 页无评论数据，结束抓取")
                break

            all_reviews.extend(page_reviews)
            print(f"[taobao] 已抓取 {len(all_reviews)} 条评论（第 {page} 页）")
            page += 1

        return all_reviews[:max_reviews]


    def extract_reviews_from_page(self, page_source: str, product_url: str,
                                   product_id: str) -> list:
        """
        从淘宝/天猫页面HTML中提取评论数据（含溯源字段）。

        :param page_source: 页面HTML源码
        :param product_url: 商品页面URL
        :param product_id: 商品ID
        :return: 评论列表（每条包含溯源字段）
        """
        import re
        from bs4 import BeautifulSoup

        reviews = []
        soup = BeautifulSoup(page_source, "html.parser")

        # 查找评论项
        rate_items = soup.select('[class*="rate-item"], [class*="RateItem"], [class*="comment-item"]')

        for item in rate_items:
            text = item.get_text(strip=True)

            # 提取用户名
            reviewer_match = re.search(r'([\u4e00-\u9fa5a-zA-Z0-9\*]{2,20})\s+\d{4}', text)
            reviewer_name = reviewer_match.group(1) if reviewer_match else "匿名买家"

            # 提取日期
            date_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2})', text)
            review_date = date_match.group(1) if date_match else ""

            # 提取SKU
            sku_match = re.search(r'已购：(.+?)(?:\s|$)', text)
            sku = sku_match.group(1) if sku_match else ""

            # 提取评论内容（去掉用户名、日期、SKU后的部分）
            content = text
            if reviewer_match:
                content = content.replace(reviewer_match.group(0), "")
            if date_match:
                content = content.replace(date_match.group(0), "")
            if sku_match:
                content = content.replace(sku_match.group(0), "")
            content = content.strip()[:500]

            if content and len(content) > 2:
                review = {
                    "review_text": content,
                    "rating": 5,  # 默认5星，实际应从页面提取
                    "platform": "taobao",
                    # 溯源字段
                    "source_platform": "taobao",
                    "source_url": product_url,
                    "product_id": product_id,
                    "review_permalink": f"{product_url}#review",
                    "reviewer_name": reviewer_name,
                    "reviewer_id": "",  # 平台脱敏ID
                    "review_date": review_date,
                    "sku": sku,
                    "is_demo": False,  # 真实评论，非演示数据
                }
                reviews.append(review)

        return reviews

    def scrape_with_cookies(self, product_url: str, cookies: dict,
                             max_reviews: int = 50) -> list:
        """
        使用Cookie抓取淘宝/天猫评论（含mtop签名）。
        """
        import re
        import requests
        import hashlib
        import json as _json

        # 1. URL清洗：从分享文本中提取纯URL
        if not product_url:
            return []
        url_match = re.search(r'https?://[^\s一-龥（）「」]+', product_url)
        if url_match:
            product_url = url_match.group(0).strip('.,;\'"')
        print(f"[taobao] 清洗后URL: {product_url}")

        # 2. 短链解析
        if 'tb.cn' in product_url or 'tb.com' in product_url:
            print(f"[taobao] 解析短链: {product_url}")
            try:
                resp = requests.get(
                    product_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                      "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                    },
                    allow_redirects=True,
                    timeout=15,
                )
                final_url = resp.url
                print(f"[taobao] 短链跳转到: {final_url}")
                # 从最终URL提取item_id
                item_id = self.parse_item_id(final_url)
                if not item_id:
                    # 从页面内容中提取
                    id_match = re.search(r'[?&]id=(\d+)', resp.text)
                    if id_match:
                        item_id = id_match.group(1)
                if not item_id:
                    print("[taobao] 无法提取商品ID")
                    return []
                product_url = f"https://item.taobao.com/item.htm?id={item_id}"
            except Exception as e:
                print(f"[taobao] 短链解析失败: {e}")
                return []
        else:
            item_id = self.parse_item_id(product_url)
            if not item_id:
                print(f"[taobao] 无法提取商品ID: {product_url}")
                return []

        print(f"[taobao] 商品ID: {item_id}")

        # 3. 获取商品名称
        product_name = ""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                "Referer": product_url,
            }
            page_resp = requests.get(
                f"https://item.taobao.com/item.htm?id={item_id}",
                cookies=cookies,
                headers=headers,
                timeout=15,
            )
            if page_resp.status_code == 200:
                title_match = re.search(r'<title>(.*?)</title>', page_resp.text)
                if title_match:
                    product_name = title_match.group(1).split("-")[0].strip()
                print(f"[taobao] 商品名: {product_name}")
        except Exception:
            pass

        # 4. 生成mtop签名并调用评论API
        tk = cookies.get("_m_h5_tk", "")
        token = tk.split("_")[0] if tk else ""
        if not token:
            print("[taobao] 警告: Cookie中缺少_m_h5_tk，尝试无签名请求")

        reviews = []
        t = str(int(time.time() * 1000))
        appKey = "12574478"

        # 评论API请求
        for page in range(1, max_reviews // 20 + 5):  # 按目标量动态计算页数
            data_str = _json.dumps({
                "auctionNumId": item_id,
                "currentPageNum": page,
                "pageSize": 20,
                "rateType": "",
                "orderType": 0,
            }, ensure_ascii=False, separators=(',', ':'))

            # 生成签名: md5(token + '&' + t + '&' + appKey + '&' + data)
            sign_str = f"{token}&{t}&{appKey}&{data_str}"
            sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()

            params = {
                "jsv": "2.7.2",
                "appKey": appKey,
                "t": t,
                "sign": sign,
                "api": "mtop.taobao.rate.detaillist.get",
                "v": "6.0",
                "type": "originaljson",
                "dataType": "json",
                "data": data_str,
            }

            api_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                "Referer": f"https://h5.m.taobao.com/awp/core/detail.htm?id={item_id}",
                "Origin": "https://h5.m.taobao.com",
            }

            try:
                api_resp = requests.get(
                    self.RATE_API,
                    params=params,
                    cookies=cookies,
                    headers=api_headers,
                    timeout=15,
                )
                print(f"[taobao] API第{page}页状态码: {api_resp.status_code}")

                if api_resp.status_code != 200:
                    break

                # 解析响应
                text = api_resp.text.strip()
                # 去除JSONP包裹
                jsonp_match = re.match(r"^[a-zA-Z0-9_]+\((.*)\);?$", text, re.DOTALL)
                if jsonp_match:
                    text = jsonp_match.group(1)

                try:
                    result = _json.loads(text)
                except _json.JSONDecodeError:
                    print(f"[taobao] 第{page}页JSON解析失败")
                    break

                # 检查API返回
                ret_code = result.get("ret", [])
                if ret_code and "FAIL_SYS" in str(ret_code):
                    print(f"[taobao] API返回错误: {ret_code}")
                    break

                rate_list = result.get("data", {}).get("rateList", [])
                if not rate_list:
                    print(f"[taobao] 第{page}页无评论数据")
                    break

                for item in rate_list:
                    review_text = (item.get("feedback") or item.get("content") or "").strip()
                    if not review_text:
                        continue
                    review = {
                        "review_text": review_text,
                        "rating": int(item.get("rateScore", 5)) if item.get("rateScore") else 5,
                        "platform": "taobao",
                        "product_name": product_name,
                        "timestamp": item.get("rateDate", ""),
                        "user_id": str(item.get("userNick") or item.get("displayUserNick") or ""),
                        # 溯源字段
                        "source_platform": "taobao",
                        "source_url": product_url,
                        "product_id": item_id,
                        "review_permalink": f"{product_url}#review",
                        "reviewer_name": str(item.get("displayUserNick") or item.get("userNick") or "匿名"),
                        "reviewer_id": str(item.get("displayUserNumId") or ""),
                        "review_date": item.get("rateDate", ""),
                        "sku": item.get("auctionSku", ""),
                        "is_demo": False,
                    }
                    reviews.append(review)

                print(f"[taobao] 第{page}页获取{len(rate_list)}条评论，累计{len(reviews)}条")
                time.sleep(1.5)  # 避免触发反爬

                if len(reviews) >= max_reviews:
                    break

            except Exception as e:
                print(f"[taobao] 第{page}页请求失败: {e}")
                break

        # 5. 如果API获取失败，尝试从商品页面HTML中提取评论
        if not reviews:
            print("[taobao] API获取失败，尝试从页面HTML提取评论...")
            try:
                page_resp = requests.get(
                    product_url,
                    cookies=cookies,
                    headers=headers,
                    timeout=15,
                )
                if page_resp.status_code == 200:
                    reviews = self.extract_reviews_from_page(
                        page_resp.text, product_url, item_id
                    )
                    for r in reviews:
                        r["product_name"] = product_name
                    print(f"[taobao] HTML提取到{len(reviews)}条评论")
            except Exception as e:
                print(f"[taobao] HTML提取失败: {e}")

        print(f"[taobao] 共抓取 {len(reviews)} 条真实评论")
        return reviews[:max_reviews]



    # ------------------------------------------------------------------
    # Selenium 浏览器抓取（最可靠的方式）
    # ------------------------------------------------------------------
    def scrape_with_selenium(self, product_url: str, cookies: dict,
                             max_reviews: int = 50) -> list:
        """
        使用 Selenium 浏览器抓取淘宝评论。

        通过真实浏览器渲染页面，自动处理 mtop 签名和反爬机制。
        这是目前最可靠的淘宝评论抓取方式。

        :param product_url: 商品 URL 或分享文本
        :param cookies: 登录 Cookie 字典
        :param max_reviews: 最大评论数
        :return: 评论列表（含完整溯源字段）
        """
        import re
        import time
        import json as _json

        # 1. URL 清洗
        if not product_url:
            return []
        url_match = re.search(r'https?://[^\s一-龥（）「」]+', product_url)
        if url_match:
            product_url = url_match.group(0).strip('.,;\'"')

        # 2. 短链解析
        if 'tb.cn' in product_url or 'tb.com' in product_url:
            import requests
            try:
                resp = requests.get(product_url, allow_redirects=True, timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"})
                final_url = resp.url
                item_id = self.parse_item_id(final_url)
                if not item_id:
                    id_match = re.search(r'[?&]id=(\d+)', resp.text)
                    if id_match:
                        item_id = id_match.group(1)
            except Exception as e:
                print(f"[taobao] 短链解析失败: {e}")
                return []
        else:
            item_id = self.parse_item_id(product_url)

        if not item_id:
            print("[taobao] Selenium: 无法提取商品ID")
            return []

        print(f"[taobao] Selenium模式启动: 商品ID={item_id}")

        # 3. 启动 Selenium
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
        except ImportError:
            print("[taobao] Selenium 未安装，无法使用浏览器抓取")
            return []

        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        try:
            # Selenium 4 内置驱动管理器，自动匹配 Chrome 版本
            driver = webdriver.Chrome(options=options)
        except Exception as e:
            print(f"[taobao] Chrome 启动失败: {e}")
            return []

        reviews = []
        product_name = ""
        product_page_url = f"https://item.taobao.com/item.htm?id={item_id}"

        try:
            # 4. 先打开淘宝域名（设置 Cookie 的前提）
            driver.get("https://www.taobao.com/")
            time.sleep(2)

            # 5. 注入 Cookie
            for name, value in cookies.items():
                try:
                    driver.add_cookie({
                        "name": name,
                        "value": value,
                        "domain": ".taobao.com",
                    })
                except Exception:
                    pass
            print(f"[taobao] 已注入 {len(cookies)} 个 Cookie")

            # 6. 注入网络拦截脚本（捕获 mtop API 响应）
            interceptor_js = """
            window.__capturedReviews = [];
            var origOpen = XMLHttpRequest.prototype.open;
            var origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(m, u) {
                this._url = u;
                return origOpen.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function() {
                var self = this;
                this.addEventListener('load', function() {
                    if (self._url && (self._url.indexOf('rate') !== -1 ||
                        self._url.indexOf('mtop.taobao.rate') !== -1)) {
                        try {
                            var text = self.responseText;
                            var match = text.match(/^[a-zA-Z0-9_]+\\((.+)\\);?$/);
                            var jsonStr = match ? match[1] : text;
                            window.__capturedReviews.push(JSON.parse(jsonStr));
                        } catch(e) {}
                    }
                });
                return origSend.apply(this, arguments);
            };
            """
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": interceptor_js},
            )

            # 7. 导航到商品页面
            driver.get(product_page_url)
            time.sleep(4)

            # 获取商品名
            try:
                product_name = driver.title.split("-")[0].strip() if driver.title else ""
            except Exception:
                pass
            print(f"[taobao] 商品名: {product_name}")

            # 8. 尝试点击"评价"标签
            for xpath in [
                '//a[contains(text(),"评价")]',
                '//span[contains(text(),"评价")]',
                '//li[contains(text(),"评价")]',
                '//div[contains(text(),"评价")]',
            ]:
                try:
                    els = driver.find_elements(By.XPATH, xpath)
                    for el in els:
                        if el.is_displayed():
                            el.click()
                            time.sleep(2)
                            break
                except Exception:
                    pass

            # 9. 尝试点击"全部评价"/"全部评论"
            try:
                els = driver.find_elements(By.XPATH,
                    '//a[contains(text(),"全部评价")] | '
                    '//a[contains(text(),"全部评论")] | '
                    '//span[contains(text(),"全部评价")]')
                for el in els:
                    if el.is_displayed():
                        el.click()
                        time.sleep(2)
                        break
            except Exception:
                pass

            # 10. 滚动触发懒加载
            for _ in range(3):
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(1)
            time.sleep(2)

            # 11. 优先从拦截的 API 响应中提取评论
            captured = driver.execute_script("return window.__capturedReviews || [];")
            if captured:
                print(f"[taobao] 拦截到 {len(captured)} 个 API 响应")
                for cap in captured:
                    if not isinstance(cap, dict):
                        continue
                    rate_list = cap.get("data", {}).get("rateList", [])
                    for item in rate_list:
                        review_text = (item.get("feedback") or
                                       item.get("content") or "").strip()
                        if not review_text:
                            continue
                        reviews.append({
                            "review_text": review_text,
                            "rating": int(item.get("rateScore", 5)) if item.get("rateScore") else 5,
                            "platform": "taobao",
                            "product_name": product_name,
                            "timestamp": item.get("rateDate", ""),
                            "user_id": str(item.get("userNick") or
                                          item.get("displayUserNick") or ""),
                            "source_platform": "taobao",
                            "source_url": product_page_url,
                            "product_id": item_id,
                            "review_permalink": f"{product_page_url}#review",
                            "reviewer_name": str(item.get("displayUserNick") or
                                                item.get("userNick") or "匿名"),
                            "reviewer_id": str(item.get("displayUserNumId") or ""),
                            "review_date": item.get("rateDate", ""),
                            "sku": item.get("auctionSku", ""),
                            "is_demo": False,
                        })

            # 12. 如果拦截没有数据，从渲染的 DOM 中提取
            if not reviews:
                page_source = driver.page_source
                reviews = self._extract_reviews_from_dom(
                    page_source, product_page_url, item_id, product_name)

            # 13. 如果 DOM 也没有，尝试从 iframe 中提取
            if not reviews:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        iframe_src = driver.page_source
                        iframe_reviews = self._extract_reviews_from_dom(
                            iframe_src, product_page_url, item_id, product_name)
                        reviews.extend(iframe_reviews)
                        driver.switch_to.default_content()
                        if len(reviews) >= max_reviews:
                            break
                    except Exception:
                        driver.switch_to.default_content()

            print(f"[taobao] Selenium 共抓取 {len(reviews)} 条真实评论")

        except Exception as e:
            print(f"[taobao] Selenium 抓取异常: {e}")
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        return reviews[:max_reviews]

    def _extract_reviews_from_dom(self, page_source: str, product_url: str,
                                   item_id: str, product_name: str) -> list:
        """从 Selenium 渲染后的 DOM 中提取评论数据。"""
        from bs4 import BeautifulSoup
        import re

        reviews = []
        soup = BeautifulSoup(page_source, "html.parser")

        # 尝试多种 CSS 选择器（淘宝类名经常变化）
        selectors = [
            '[class*="rate-item"]',
            '[class*="Comment--"]',
            '[class*="comment-item"]',
            '[class*="review-item"]',
            '[class*="rateContent"]',
            '[class*="rate-content"]',
        ]

        for selector in selectors:
            items = soup.select(selector)
            if not items:
                continue
            for item in items:
                text = item.get_text(strip=True, separator=" ")
                if len(text) < 5:
                    continue

                # 提取用户名
                reviewer = "匿名"
                for sel in ['[class*="user"]', '[class*="User"]',
                            '[class*="nick"]', '[class*="Nick"]']:
                    el = item.select_one(sel)
                    if el:
                        reviewer = el.get_text(strip=True)
                        break

                # 提取日期
                date = ""
                date_match = re.search(
                    r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', text)
                if date_match:
                    date = date_match.group(1)

                # 提取评分
                rating = 5
                rating_match = re.search(r'(\d)\s*星|评分[::](\d)', text)
                if rating_match:
                    rating = int(rating_match.group(1) or rating_match.group(2))

                # 提取 SKU
                sku = ""
                sku_match = re.search(r'(?:已购|sku)[::]\s*(.+?)(?:\s|$)', text,
                                      re.IGNORECASE)
                if sku_match:
                    sku = sku_match.group(1)

                # 清理评论内容
                content = text
                if reviewer != "匿名":
                    content = content.replace(reviewer, "")
                if date:
                    content = content.replace(date, "")
                content = re.sub(r'^\d+\s*星?\s*', '', content).strip()

                if content and len(content) > 3:
                    reviews.append({
                        "review_text": content[:500],
                        "rating": rating,
                        "platform": "taobao",
                        "product_name": product_name,
                        "timestamp": date,
                        "user_id": reviewer,
                        "source_platform": "taobao",
                        "source_url": product_url,
                        "product_id": item_id,
                        "review_permalink": f"{product_url}#review",
                        "reviewer_name": reviewer,
                        "reviewer_id": "",
                        "review_date": date,
                        "sku": sku,
                        "is_demo": False,
                    })
            if reviews:
                break

        return reviews

    # ------------------------------------------------------------------
    # 交互式浏览器抓取（登录+抓取一体化，最可靠）
    # ------------------------------------------------------------------
    def scrape_interactive(self, product_url: str, cookies: dict = None,
                           max_reviews: int = 50) -> list:
        """
        交互式浏览器抓取：打开 Chrome → 注入Cookie(如有) → 打开商品页 →
        自动点击评价 → 拦截API响应/DOM提取评论。

        与 scrape_with_selenium 的区别：
        - 同时拦截 XMLHttpRequest 和 fetch
        - 尝试桌面版和移动版两个页面
        - 更长的等待时间和更多滚动次数
        - 更详细的日志输出

        :param product_url: 商品 URL 或分享文本
        :param cookies: 登录 Cookie（可选，没有则提示用户在浏览器中登录）
        :param max_reviews: 最大评论数
        :return: 评论列表（含完整溯源字段）
        """
        import re
        import time
        import json as _json

        # 1. URL 清洗
        if not product_url:
            return []
        url_match = re.search(r'https?://[^\s一-龥（）「」]+', product_url)
        if url_match:
            product_url = url_match.group(0).strip('.,;\'"')

        # 2. 短链解析
        if 'tb.cn' in product_url or 'tb.com' in product_url:
            import requests
            try:
                resp = requests.get(product_url, allow_redirects=True, timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"})
                final_url = resp.url
                item_id = self.parse_item_id(final_url)
                if not item_id:
                    id_match = re.search(r'[?&]id=(\d+)', resp.text)
                    if id_match:
                        item_id = id_match.group(1)
                print(f"[taobao] 短链解析: {product_url} -> {final_url}")
            except Exception as e:
                print(f"[taobao] 短链解析失败: {e}")
                return []
        else:
            item_id = self.parse_item_id(product_url)

        if not item_id:
            print("[taobao] 交互模式: 无法提取商品ID")
            return []

        print(f"[taobao] 交互模式启动: 商品ID={item_id}")

        # 3. 启动 Selenium
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except ImportError:
            print("[taobao] Selenium 未安装")
            return []

        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        # 设置窗口大小
        options.add_argument("--window-size=1280,900")

        try:
            # Selenium 4 内置驱动管理器，自动匹配 Chrome 版本
            driver = webdriver.Chrome(options=options)
        except Exception as e:
            print(f"[taobao] Chrome 启动失败: {e}")
            return []

        # 去除 webdriver 标记
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
        except Exception:
            pass

        reviews = []
        product_name = ""
        product_page_url = f"https://item.taobao.com/item.htm?id={item_id}"

        try:
            # 4. 先打开淘宝首页
            driver.get("https://www.taobao.com/")
            time.sleep(2)

            # 5. 注入 Cookie（如果有）
            if cookies:
                for name, value in cookies.items():
                    try:
                        driver.add_cookie({
                            "name": name,
                            "value": value,
                            "domain": ".taobao.com",
                        })
                    except Exception:
                        pass
                print(f"[taobao] 已注入 {len(cookies)} 个 Cookie")

            # 6. 注入网络拦截脚本（同时拦截 XHR 和 fetch）
            interceptor_js = r"""
            window.__capturedReviews = [];
            // 拦截 XMLHttpRequest
            var origOpen = XMLHttpRequest.prototype.open;
            var origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(m, u) {
                this._url = u;
                return origOpen.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function() {
                var self = this;
                this.addEventListener('load', function() {
                    try {
                        if (self._url && (self._url.indexOf('rate') !== -1 ||
                            self._url.indexOf('comment') !== -1 ||
                            self._url.indexOf('mtop.taobao') !== -1)) {
                            var text = self.responseText;
                            var m = text.match(/^[a-zA-Z0-9_]+\((.+)\);?$/);
                            var s = m ? m[1] : text;
                            window.__capturedReviews.push({url: self._url, data: JSON.parse(s)});
                        }
                    } catch(e) {}
                });
                return origSend.apply(this, arguments);
            };
            // 拦截 fetch
            var origFetch = window.fetch;
            window.fetch = function() {
                var url = arguments[0];
                if (typeof url === 'object') url = url.url || '';
                return origFetch.apply(this, arguments).then(function(resp) {
                    try {
                        if (url && (url.indexOf('rate') !== -1 ||
                            url.indexOf('comment') !== -1 ||
                            url.indexOf('mtop.taobao') !== -1)) {
                            resp.clone().text().then(function(text) {
                                var m = text.match(/^[a-zA-Z0-9_]+\((.+)\);?$/);
                                var s = m ? m[1] : text;
                                window.__capturedReviews.push({url: url, data: JSON.parse(s)});
                            });
                        }
                    } catch(e) {}
                    return resp;
                });
            };
            """
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": interceptor_js},
            )

            # 7. 导航到商品页面
            print(f"[taobao] 正在打开商品页面: {product_page_url}")
            driver.get(product_page_url)
            time.sleep(5)

            # 获取商品名
            try:
                product_name = driver.title.split("-")[0].strip() if driver.title else ""
            except Exception:
                pass
            print(f"[taobao] 商品名: {product_name}")

            # 8. 检查是否被重定向到登录页面（无论是否注入了Cookie都检查）
            current_url = driver.current_url
            page_title = driver.title or ""
            is_login_page = ("login" in current_url.lower() or
                             "登录" in page_title or
                             "login" in page_title.lower() or
                             "login.taobao" in current_url.lower())
            print(f"[taobao] 当前页面标题: {page_title}")
            print(f"[taobao] 当前URL: {current_url[:80]}")

            if is_login_page:
                print("[taobao] ========================================")
                print("[taobao] 检测到需要登录！")
                print("[taobao] 请在弹出的浏览器窗口中完成淘宝登录")
                print("[taobao] 登录后系统会自动继续抓取评论...")
                print("[taobao] ========================================")
                # 等待用户登录（最多180秒）
                login_success = False
                for i in range(90):
                    time.sleep(2)
                    try:
                        current_url = driver.current_url
                        page_title = driver.title or ""
                        if ("login" not in current_url.lower() and
                            "登录" not in page_title and
                            "login.taobao" not in current_url.lower()):
                            print(f"[taobao] 登录成功！当前页面: {page_title}")
                            login_success = True
                            break
                    except Exception:
                        pass
                    if i % 15 == 0 and i > 0:
                        print(f"[taobao] 仍在等待登录... ({i*2}秒)")

                if not login_success:
                    print("[taobao] 登录超时（180秒）")

                # 登录后重新导航到商品页面
                print(f"[taobao] 重新打开商品页面: {product_page_url}")
                driver.get(product_page_url)
                time.sleep(5)
                # 重新获取商品名
                try:
                    product_name = driver.title.split("-")[0].strip() if driver.title else ""
                    print(f"[taobao] 商品名: {product_name}")
                except Exception:
                    pass

            # 9. 尝试点击"评价"/"累计评论"标签
            print("[taobao] 尝试点击评价标签...")
            clicked = False
            for xpath in [
                '//a[contains(text(),"评价")]',
                '//a[contains(text(),"累计评论")]',
                '//span[contains(text(),"评价")]',
                '//li[contains(text(),"评价")]',
                '//div[contains(text(),"评价")]',
                '//a[contains(text(),"宝贝评价")]',
            ]:
                try:
                    els = driver.find_elements(By.XPATH, xpath)
                    for el in els:
                        if el.is_displayed():
                            el.click()
                            print(f"[taobao] 点击了: {el.text}")
                            clicked = True
                            time.sleep(3)
                            break
                except Exception:
                    pass
                if clicked:
                    break

            # 10. 尝试点击"全部评价"
            try:
                els = driver.find_elements(By.XPATH,
                    '//a[contains(text(),"全部评价")] | '
                    '//a[contains(text(),"全部评论")] | '
                    '//span[contains(text(),"全部评价")] | '
                    '//span[contains(text(),"全部评论")]')
                for el in els:
                    if el.is_displayed():
                        el.click()
                        print(f"[taobao] 点击了: {el.text}")
                        time.sleep(3)
                        break
            except Exception:
                pass

            # 11. 滚动页面触发懒加载
            print("[taobao] 滚动页面加载更多评论...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1.5)

            # 等待评论加载
            time.sleep(3)

            # 12. 优先从拦截的 API 响应中提取评论
            captured = driver.execute_script("return window.__capturedReviews || [];")
            if captured:
                print(f"[taobao] 拦截到 {len(captured)} 个 API 响应")
                for cap in captured:
                    if not isinstance(cap, dict):
                        continue
                    cap_data = cap.get("data", cap)
                    if not isinstance(cap_data, dict):
                        continue
                    rate_list = cap_data.get("data", {}).get("rateList", [])
                    if not rate_list:
                        # 尝试其他可能的数据结构
                        rate_list = cap_data.get("rateList", [])
                    for item in rate_list:
                        review_text = (item.get("feedback") or
                                       item.get("content") or "").strip()
                        if not review_text:
                            continue
                        reviews.append({
                            "review_text": review_text,
                            "rating": int(item.get("rateScore", 5)) if item.get("rateScore") else 5,
                            "platform": "taobao",
                            "product_name": product_name,
                            "timestamp": item.get("rateDate", ""),
                            "user_id": str(item.get("userNick") or
                                          item.get("displayUserNick") or ""),
                            "source_platform": "taobao",
                            "source_url": product_page_url,
                            "product_id": item_id,
                            "review_permalink": f"{product_page_url}#review",
                            "reviewer_name": str(item.get("displayUserNick") or
                                                item.get("userNick") or "匿名"),
                            "reviewer_id": str(item.get("displayUserNumId") or ""),
                            "review_date": item.get("rateDate", ""),
                            "sku": item.get("auctionSku", ""),
                            "is_demo": False,
                        })
                if reviews:
                    print(f"[taobao] 从API拦截获取 {len(reviews)} 条评论")

            # 13. 如果拦截没有数据，从渲染的 DOM 中提取
            if not reviews:
                print("[taobao] API拦截无数据，尝试从DOM提取...")
                page_source = driver.page_source
                reviews = self._extract_reviews_from_dom(
                    page_source, product_page_url, item_id, product_name)
                if reviews:
                    print(f"[taobao] 从DOM提取 {len(reviews)} 条评论")

            # 14. 尝试从 iframe 中提取
            if not reviews:
                print("[taobao] DOM无数据，尝试iframe...")
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                print(f"[taobao] 发现 {len(iframes)} 个 iframe")
                for idx, iframe in enumerate(iframes):
                    try:
                        driver.switch_to.frame(iframe)
                        iframe_src = driver.page_source
                        iframe_reviews = self._extract_reviews_from_dom(
                            iframe_src, product_page_url, item_id, product_name)
                        if iframe_reviews:
                            reviews.extend(iframe_reviews)
                            print(f"[taobao] iframe#{idx} 提取 {len(iframe_reviews)} 条")
                        driver.switch_to.default_content()
                    except Exception:
                        driver.switch_to.default_content()

            # 15. 保存最新 Cookie（如果有）
            if cookies:
                try:
                    selenium_cookies = driver.get_cookies()
                    fresh_cookies = {}
                    for c in selenium_cookies:
                        name = c.get("name", "")
                        value = c.get("value", "")
                        if name and value:
                            fresh_cookies[name] = value
                    if fresh_cookies:
                        import os
                        cookie_dir = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "cookies")
                        os.makedirs(cookie_dir, exist_ok=True)
                        cookie_path = os.path.join(cookie_dir, "taobao_cookies.json")
                        with open(cookie_path, "w", encoding="utf-8") as f:
                            _json.dump({
                                "platform": "taobao",
                                "cookies": fresh_cookies,
                                "saved_at": time.time(),
                                "source": "selenium_interactive",
                            }, f, ensure_ascii=False, indent=2)
                        print(f"[taobao] 已保存最新Cookie ({len(fresh_cookies)} 个)")
                except Exception as e:
                    print(f"[taobao] 保存Cookie失败: {e}")

            print(f"[taobao] 交互模式共抓取 {len(reviews)} 条真实评论")

        except Exception as e:
            import traceback
            print(f"[taobao] 交互模式异常: {e}")
            traceback.print_exc()
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        return reviews[:max_reviews]
