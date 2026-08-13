# -*- coding: utf-8 -*-
"""
淘宝评论爬虫 V2 — 基于 taobaocomment 项目的现代化改造版
=========================================================
原始项目: https://github.com/a707937337/taobaocomment (hunterhug, 2015/11)
改造内容:
  1. 移除硬编码凭据和远程 MySQL 鉴权（安全修复）
  2. 适配 Python 3.8+（time.clock → time.perf_counter）
  3. 改用 UTF-8 解码（现代淘宝页面编码）
  4. 添加完整溯源字段（source_platform/source_url/product_id 等）
  5. 添加反虚假评论验证
  6. 支持 Cookie 注入和自动重试
  7. 输出标准 JSON 格式（兼容项目其他模块）

API 端点:
  - 淘宝: rate.taobao.com/feedRateList.htm
  - 天猫: rate.tmall.com/list_detail_rate.htm

使用方式:
  from scrapers.taobao_comment_v2 import TaobaoCommentScraperV2
  scraper = TaobaoCommentScraperV2()
  reviews = scraper.scrape(product_url, cookies=cookie_dict, max_reviews=50)
"""

import os
import re
import json
import time
import logging
import requests
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlencode, urlparse, parse_qs

logger = logging.getLogger(__name__)

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TaobaoCommentScraperV2:
    """
    淘宝/天猫评论爬虫 V2

    基于 a707937337/taobaocomment 项目的 API 调用方式，
    进行现代化改造，添加溯源字段和反虚假评论机制。

    抓取优先级:
    1. rate.taobao.com API（快速，需有效 Cookie）
    2. 降级到 Selenium 浏览器抓取（由调用方处理）
    """

    # API 端点
    TAOBAO_RATE_API = "https://rate.taobao.com/feedRateList.htm"
    TMALL_RATE_API = "https://rate.tmall.com/list_detail_rate.htm"
    ITEM_PAGE = "https://item.taobao.com/item.htm"

    # 请求头 — 模拟真实浏览器
    HEADERS = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/124.0.0.0 Safari/537.36'),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.taobao.com/',
        'Connection': 'keep-alive',
        'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Upgrade-Insecure-Requests': '1',
    }

    def __init__(self, delay: float = 1.5, timeout: int = 15, max_retries: int = 3):
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _resolve_short_link(self, url: str) -> str:
        """解析淘宝短链，返回最终URL"""
        if not url:
            return url
        # 检测是否为短链
        if 'tb.cn' not in url and 'tb.com' not in url:
            return url
        try:
            resp = requests.get(
                url,
                allow_redirects=True,
                timeout=15,
                headers={
                    'User-Agent': self.HEADERS['User-Agent'],
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                },
            )
            final_url = resp.url
            logger.info(f"短链解析: {url} -> {final_url}")
            return final_url
        except Exception as e:
            logger.error(f"短链解析失败: {e}")
            return url

    def _extract_product_id(self, url: str) -> Tuple[str, str]:
        """
        从商品 URL 中提取商品 ID 和平台类型

        支持的 URL 格式:
        - https://item.taobao.com/item.htm?id=123456
        - https://detail.tmall.com/item.htm?id=123456
        - https://a.m.taobao.com/i123456.htm
        - 短链（需调用方先解析）

        返回: (product_id, platform)  platform: "taobao" 或 "tmall"
        """
        # 清理 URL
        url = url.strip()

        # 检测平台
        platform = "taobao"
        if 'tmall.com' in url:
            platform = "tmall"

        # 提取商品 ID
        product_id = ""

        # ?id=123456 格式
        match = re.search(r'[?&]id=(\d+)', url)
        if match:
            product_id = match.group(1)
        else:
            # a.m.taobao.com/i123456.htm 格式
            match = re.search(r'/i(\d+)\.htm', url)
            if match:
                product_id = match.group(1)
            else:
                # itemId=123456 格式
                match = re.search(r'itemId=(\d+)', url)
                if match:
                    product_id = match.group(1)

        if not product_id:
            # 尝试从 URL 路径中提取数字
            match = re.search(r'(\d{8,})', url)
            if match:
                product_id = match.group(1)

        return product_id, platform

    def _get_seller_id(self, product_id: str, cookies: Dict) -> str:
        """
        从商品页面获取卖家 ID（userNumId/sellerId）

        尝试多个来源：
        1. 桌面版商品页面 item.taobao.com
        2. 移动版商品页面 h5.m.taobao.com
        3. mtop detail API
        """
        # 方法1: 桌面版商品页面
        seller_id = self._get_seller_id_from_page(
            f"{self.ITEM_PAGE}?id={product_id}", cookies)
        if seller_id:
            return seller_id

        # 方法2: 移动版商品页面（反爬较松）
        seller_id = self._get_seller_id_from_page(
            f"https://h5.m.taobao.com/awp/core/detail.htm?id={product_id}", cookies)
        if seller_id:
            return seller_id

        # 方法3: mtop detail API
        try:
            api_url = f"https://h5api.m.taobao.com/h5/mtop.taobao.detail.getdetail/6.0/?data=%7B%22itemNumId%22%3A%22{product_id}%22%7D"
            resp = self.session.get(api_url, cookies=cookies, timeout=self.timeout)
            text = resp.text.strip()
            # 去除JSONP包裹
            jsonp_match = re.match(r'^[a-zA-Z0-9_]+\((.*)\);?$', text, re.DOTALL)
            if jsonp_match:
                text = jsonp_match.group(1)
            data = json.loads(text)
            seller_id = str(data.get("data", {}).get("item", {}).get("sellerId", ""))
            if seller_id and seller_id != "0":
                logger.info(f"从mtop API获取卖家ID: {seller_id}")
                return seller_id
        except Exception as e:
            logger.debug(f"mtop API获取卖家ID失败: {e}")

        logger.warning(f"无法从商品页面提取卖家ID (product_id={product_id})")
        return ""

    def _get_seller_id_from_page(self, url: str, cookies: Dict) -> str:
        """从指定页面URL提取卖家ID"""
        try:
            resp = self.session.get(url, cookies=cookies, timeout=self.timeout)
            html = resp.text

            # 方法1: microscope-data meta 标签
            match = re.search(r'microscope-data.*?userid=(\d+)', html)
            if match:
                logger.info(f"从microscope-data提取卖家ID: {match.group(1)}")
                return match.group(1)

            # 方法2: sellerId 变量
            match = re.search(r'sellerId["\s:=]+["\']?(\d+)', html)
            if match:
                logger.info(f"从sellerId提取卖家ID: {match.group(1)}")
                return match.group(1)

            # 方法3: userNumId 变量
            match = re.search(r'userNumId["\s:=]+["\']?(\d+)', html)
            if match:
                logger.info(f"从userNumId提取卖家ID: {match.group(1)}")
                return match.group(1)

            # 方法4: JSON 数据中的 sellerId
            match = re.search(r'"sellerId"\s*:\s*"?(\d+)"?', html)
            if match:
                logger.info(f"从JSON sellerId提取卖家ID: {match.group(1)}")
                return match.group(1)

            # 方法5: shopId/userId
            match = re.search(r'"userId"\s*:\s*"?(\d{6,})"', html)
            if match:
                logger.info(f"从userId提取卖家ID: {match.group(1)}")
                return match.group(1)

        except Exception as e:
            logger.debug(f"从页面提取卖家ID失败 ({url}): {e}")

        return ""

    def _parse_taobao_response(self, raw_text: str) -> List[Dict]:
        """
        解析淘宝评论 API 响应

        原始项目: rate.taobao.com 返回 ({"comments":[...]}) 格式
        现代改造: 兼容多种响应格式
        """
        # 清理可能的 JSONP 包装
        text = raw_text.strip()
        if text.startswith('('):
            text = text[1:]
        if text.endswith(')'):
            text = text[:-1]
        if text.endswith(');'):
            text = text[:-2]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"无法解析淘宝评论API响应: {raw_text[:200]}")
            return []

        comments = data.get('comments') or []
        if not comments and 'data' in data:
            comments = data['data'].get('comments', [])

        return comments

    def _parse_tmall_response(self, raw_text: str) -> List[Dict]:
        """
        解析天猫评论 API 响应

        原始项目: rate.tmall.com 返回 {"rateDetail":{"rateList":[...]}} 格式
        """
        text = raw_text.strip()
        if text.startswith('('):
            text = text[1:]
        if text.endswith(')'):
            text = text[:-1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"无法解析天猫评论API响应: {raw_text[:200]}")
            return []

        rate_detail = data.get('rateDetail', {})
        rate_list = rate_detail.get('rateList', [])

        return rate_list

    def _format_review(
        self,
        comment: Dict,
        product_id: str,
        platform: str,
        page_num: int,
        product_url: str = "",
        product_name: str = "",
    ) -> Dict:
        """
        将评论数据格式化为标准输出（含完整溯源字段）

        溯源字段:
        - source_platform: 来源平台
        - source_url: 商品 URL
        - product_id: 商品 ID
        - review_permalink: 评论链接
        - reviewer_name: 评论者昵称
        - review_date: 评论时间
        - extraction_method: 抓取方式
        """
        # 提取评论内容
        content = comment.get('content', '').strip()
        if not content:
            content = comment.get('rateContent', '').strip()

        # 提取评论者信息
        user_info = comment.get('user', {})
        nick = user_info.get('nick', '') or comment.get('displayUserNick', '')
        user_level = user_info.get('displayRatePic', '') or comment.get('grade', '')

        # 提取评论时间
        date = comment.get('date', '') or comment.get('rateDate', '')

        # 提取追评
        append_list = comment.get('appendList', []) or []
        append_comment = ''
        append_days = ''
        if append_list:
            first_append = append_list[0] if isinstance(append_list, list) else append_list
            append_comment = first_append.get('content', '') if isinstance(first_append, dict) else ''
            append_days = str(first_append.get('dayAfterConfirm', '')) if isinstance(first_append, dict) else ''

        # 提取商家回复
        reply = comment.get('reply')
        reply_content = ''
        if reply and isinstance(reply, dict):
            reply_content = reply.get('content', '')
        elif reply and isinstance(reply, str):
            reply_content = reply

        # 评分
        rating = comment.get('auction', {}).get('price', '') if isinstance(comment.get('auction'), dict) else ''
        rating_value = 5  # 默认5星
        if comment.get('score'):
            try:
                rating_value = int(comment['score'])
            except (ValueError, TypeError):
                pass

        return {
            # 核心字段
            'review_text': content,
            'rating': rating_value,
            'platform': '淘宝' if platform == 'taobao' else '天猫',

            # 溯源字段（必需）
            'source_platform': platform,
            'source_url': product_url or f'{self.ITEM_PAGE}?id={product_id}',
            'product_id': product_id,
            'product_name': product_name,
            'review_permalink': f'{self.ITEM_PAGE}?id={product_id}#review-{page_num}',
            'reviewer_name': nick,
            'reviewer_id': user_info.get('userId', '') if isinstance(user_info, dict) else '',
            'review_date': date,
            'sku': comment.get('sku', '') if isinstance(comment.get('sku'), str) else '',
            'page_num': page_num,
            'is_demo': False,
            'extraction_method': 'taobaocomment_v2_api',

            # 扩展字段
            'append_comment': append_comment,
            'append_days_after': append_days,
            'seller_reply': reply_content,
            'user_level': user_level,
        }

    def scrape(
        self,
        product_url: str,
        cookies: Optional[Dict] = None,
        max_reviews: int = 50,
    ) -> List[Dict]:
        """
        抓取淘宝/天猫商品评论

        参数:
            product_url: 商品 URL（支持淘宝/天猫/短链）
            cookies: 登录 Cookie 字典（可选但推荐）
            max_reviews: 最大评论数

        返回:
            评论列表（含完整溯源字段）
        """
        cookies = cookies or {}

        # Step 0: 从分享文本中提取URL
        url_match = re.search(r'https?://[^\s一-龥（）「」]+', product_url)
        if url_match:
            product_url = url_match.group(0).strip('.,;\'"')

        # Step 1: 解析短链
        if 'tb.cn' in product_url or 'tb.com' in product_url:
            logger.info(f"检测到短链，正在解析: {product_url}")
            product_url = self._resolve_short_link(product_url)

        # Step 2: 提取商品 ID 和平台
        product_id, platform = self._extract_product_id(product_url)
        if not product_id:
            logger.error(f"无法从 URL 提取商品 ID: {product_url}")
            return []

        logger.info(f"商品 ID: {product_id}, 平台: {platform}")

        # Step 3: 获取卖家 ID（可能失败，不影响后续尝试）
        seller_id = self._get_seller_id(product_id, cookies)
        logger.info(f"卖家 ID: {seller_id}")

        # Step 4: 抓取评论
        if platform == "tmall":
            reviews = self._scrape_tmall(product_id, seller_id, cookies, max_reviews, product_url)
        else:
            reviews = self._scrape_taobao(product_id, seller_id, cookies, max_reviews, product_url)

        # Step 4.5: 如果有卖家ID但抓取失败，尝试不带卖家ID重新抓取
        if not reviews and seller_id:
            logger.info("带卖家ID抓取失败，尝试不带卖家ID重新抓取...")
            reviews = self._scrape_taobao(product_id, "", cookies, max_reviews, product_url)

        # Step 4: 反虚假评论验证 — 过滤空评论
        valid_reviews = []
        for r in reviews:
            if r.get('review_text', '').strip():
                valid_reviews.append(r)

        logger.info(f"抓取完成: {len(valid_reviews)} 条有效评论 (总 {len(reviews)} 条)")
        return valid_reviews

    def _scrape_taobao(
        self,
        product_id: str,
        seller_id: str,
        cookies: Dict,
        max_reviews: int,
        product_url: str,
    ) -> List[Dict]:
        """抓取淘宝评论 — rate.taobao.com/feedRateList.htm"""
        reviews = []
        max_pages = min(200, (max_reviews // 20) + 1)  # 每页约 20 条

        # 构建请求参数 — 不带卖家ID时省略 userNumId
        for page in range(1, max_pages + 1):
            if len(reviews) >= max_reviews:
                break

            params = {
                'auctionNumId': product_id,
                'showContent': '1',
                'currentPageNum': str(page),
            }
            # 只有有卖家ID时才添加（有些商品不需要）
            if seller_id:
                params['userNumId'] = seller_id

            url = f"{self.TAOBAO_RATE_API}?{urlencode(params)}"

            # 设置针对商品页面的 Referer
            headers = {
                'Referer': f'https://item.taobao.com/item.htm?id={product_id}',
                'Accept': '*/*',
            }

            try:
                resp = self.session.get(
                    url,
                    cookies=cookies,
                    headers=headers,
                    timeout=self.timeout,
                )

                if resp.status_code != 200:
                    logger.warning(f"淘宝评论API返回 {resp.status_code} (page {page})")
                    break

                # 检测反爬页面（返回HTML而非JSON）
                text = resp.text.strip()
                if '<html' in text.lower() or '<script' in text.lower() or 'windvane' in text.lower():
                    logger.warning(f"第{page}页返回反爬页面，API可能需要登录Cookie")
                    break

                comments = self._parse_taobao_response(text)
                if not comments:
                    logger.info(f"第 {page} 页无评论数据，停止抓取")
                    break

                for comment in comments:
                    if len(reviews) >= max_reviews:
                        break
                    review = self._format_review(
                        comment, product_id, "taobao", page, product_url
                    )
                    reviews.append(review)

                logger.info(f"第 {page} 页: 获取 {len(comments)} 条评论 (累计 {len(reviews)})")
                time.sleep(self.delay)

            except requests.RequestException as e:
                logger.error(f"抓取第 {page} 页失败: {e}")
                break

        return reviews

    def _scrape_tmall(
        self,
        product_id: str,
        seller_id: str,
        cookies: Dict,
        max_reviews: int,
        product_url: str,
    ) -> List[Dict]:
        """抓取天猫评论 — rate.tmall.com/list_detail_rate.htm"""
        reviews = []
        max_pages = min(99, (max_reviews // 20) + 1)

        for page in range(1, max_pages + 1):
            if len(reviews) >= max_reviews:
                break

            params = {
                'itemId': product_id,
                'sellerId': seller_id,
                'content': '1',
                'order': '3',
                'currentPage': str(page),
            }

            url = f"{self.TMALL_RATE_API}?{urlencode(params)}"

            try:
                resp = self.session.get(
                    url,
                    cookies=cookies,
                    timeout=self.timeout,
                )

                if resp.status_code != 200:
                    logger.warning(f"天猫评论API返回 {resp.status_code} (page {page})")
                    break

                comments = self._parse_tmall_response(resp.text)
                if not comments:
                    logger.info(f"第 {page} 页无评论数据，停止抓取")
                    break

                for comment in comments:
                    if len(reviews) >= max_reviews:
                        break
                    review = self._format_review(
                        comment, product_id, "tmall", page, product_url
                    )
                    reviews.append(review)

                logger.info(f"第 {page} 页: 获取 {len(comments)} 条评论 (累计 {len(reviews)})")
                time.sleep(self.delay)

            except requests.RequestException as e:
                logger.error(f"抓取第 {page} 页失败: {e}")
                break

        return reviews

    def scrape_with_selenium_fallback(
        self,
        product_url: str,
        cookies: Optional[Dict] = None,
        max_reviews: int = 50,
    ) -> List[Dict]:
        """
        先尝试 API 抓取，失败后自动降级到 Selenium

        抓取优先级:
        1. taobaocomment V2 API（rate.taobao.com）
        2. Selenium 浏览器抓取（降级方案）
        """
        # 尝试 API 抓取
        logger.info("尝试 taobaocomment V2 API 抓取...")
        reviews = self.scrape(product_url, cookies=cookies, max_reviews=max_reviews)

        if reviews:
            return reviews

        # API 失败，降级到 Selenium
        logger.info("API 抓取无结果，降级到 Selenium 浏览器抓取...")
        try:
            from scrapers.taobao_scraper import TaobaoScraper
            selenium_scraper = TaobaoScraper()
            reviews = selenium_scraper.scrape_interactive(
                product_url, cookies=cookies, max_reviews=max_reviews
            )
        except Exception as e:
            logger.error(f"Selenium 降级也失败: {e}")

        return reviews
