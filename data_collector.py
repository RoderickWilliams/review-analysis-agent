# -*- coding: utf-8 -*-
"""
数据采集模块
====================
从电商平台和社交媒体采集用户评论数据。
支持手动导入 CSV 和简单爬虫两种方式。

使用方式:
    # 方式1: 手动导入（推荐）
    from data_collector import DataCollector
    collector = DataCollector()
    reviews = collector.load_from_csv("data/raw_reviews.csv")

    # 方式2: 爬虫采集（需遵守平台条款）
    reviews = collector.crawl_product_reviews(
        platform="taobao",
        product_id="123456",
        max_reviews=100
    )
"""

import os
import time
import json
import csv
from typing import List, Dict, Optional
from datetime import datetime

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_HTTP = True
except ImportError:
    HAS_HTTP = False

try:
    from config import CRAWL_DELAY, USER_AGENT, REQUEST_TIMEOUT, DATA_DIR
except ImportError:
    CRAWL_DELAY = 2.0
    USER_AGENT = "Mozilla/5.0"
    REQUEST_TIMEOUT = 15
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class DataCollector:
    """数据采集器：从各平台采集用户评论"""

    def __init__(self):
        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    # ═══════════════════════════════════════════════════════════════
    # 方式1：从CSV导入（推荐）
    # ═══════════════════════════════════════════════════════════════

    def load_from_csv(self, filepath: str) -> List[Dict]:
        """
        从CSV文件加载评论数据

        参数:
            filepath: CSV文件路径，需包含列:
                      review_text, rating, platform, timestamp,
                      user_id, product_name

        返回:
            评论列表，每条为字典格式
        """
        reviews = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                review = {
                    "review_text": row.get("review_text", "").strip(),
                    "rating": int(row.get("rating", 0)) if row.get("rating") else 0,
                    "platform": row.get("platform", "未知").strip(),
                    "timestamp": row.get("timestamp", "").strip(),
                    "user_id": row.get("user_id", "").strip(),
                    "product_name": row.get("product_name", "").strip(),
                }
                if review["review_text"]:
                    reviews.append(review)
        print(f"从 {filepath} 加载了 {len(reviews)} 条评论")
        return reviews

    # ═══════════════════════════════════════════════════════════════
    # 方式2：爬虫采集（需遵守平台条款）
    # ═══════════════════════════════════════════════════════════════

    def crawl_product_reviews(
        self,
        platform: str,
        product_id: str,
        max_reviews: int = 100,
        save_path: str = None,
    ) -> List[Dict]:
        """
        爬取指定平台、指定商品的评论

        参数:
            platform:   平台名称 (taobao/jd)
            product_id: 商品ID
            max_reviews: 最大采集条数
            save_path:  保存路径（None则自动生成）

        注意:
            本方法仅采集公开可见的评论数据。
            请遵守各平台的 robots.txt 和使用条款。
            建议设置合理延迟，避免对平台造成压力。
        """
        if not HAS_HTTP:
            print("错误：请先安装依赖 pip install requests beautifulsoup4")
            return []

        print(f"开始采集 {platform} 商品 {product_id} 的评论...")
        print(f"  最大采集量: {max_reviews} 条")
        print(f"  请求间隔: {CRAWL_DELAY} 秒")

        all_reviews = []

        if platform == "taobao":
            all_reviews = self._crawl_taobao(product_id, max_reviews)
        elif platform == "jd":
            all_reviews = self._crawl_jd(product_id, max_reviews)
        else:
            print(f"  不支持的平台: {platform}")
            print(f"  支持的平台: taobao, jd")
            return []

        # 保存
        if save_path is None:
            save_path = os.path.join(
                DATA_DIR, f"{platform}_{product_id}_reviews.csv"
            )
        self.save_to_csv(all_reviews, save_path)

        print(f"采集完成: 共 {len(all_reviews)} 条评论")
        print(f"已保存至: {save_path}")
        return all_reviews

    def _crawl_taobao(self, product_id: str, max_reviews: int) -> List[Dict]:
        """采集淘宝评论（示例框架）"""
        # 注意：淘宝有较强的反爬机制，实际使用需要配合登录态等
        # 这里提供框架代码，实际爬虫需根据平台API调整
        reviews = []
        page = 1

        while len(reviews) < max_reviews:
            print(f"  正在采集第 {page} 页...")
            time.sleep(CRAWL_DELAY)

            # 示例URL（实际需根据平台调整）
            # url = f"https://rate.tmall.com/list_detail_rate.htm?itemId={product_id}&currentPage={page}"
            # response = requests.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)

            # 此处为框架代码，实际使用时需要:
            # 1. 分析平台的评论API接口
            # 2. 处理反爬机制（验证码、频率限制等）
            # 3. 解析返回的JSON或HTML
            # 以下为模拟解析逻辑:

            try:
                # 实际代码示例（需根据平台调整）:
                # soup = BeautifulSoup(response.text, "html.parser")
                # items = soup.find_all("div", class_="rate-item")
                # for item in items:
                #     review = {
                #         "review_text": item.find("div", class_="rate-content").text.strip(),
                #         "rating": int(item.get("data-rate", 5)),
                #         "platform": "淘宝",
                #         "timestamp": datetime.now().isoformat(),
                #         "user_id": item.get("data-user-id", ""),
                #         "product_name": "",
                #     }
                #     reviews.append(review)

                print(f"    (框架代码 - 实际使用时需配置平台API)")
                break  # 避免无限循环

            except Exception as e:
                print(f"    采集出错: {e}")
                break

            page += 1

        return reviews[:max_reviews]

    def _crawl_jd(self, product_id: str, max_reviews: int) -> List[Dict]:
        """采集京东评论（示例框架）"""
        # 京东评论API: https://club.jd.com/comment/productPageComments.action
        # 参数: productId, page, pageSize
        # 注意：京东也有反爬机制，需要合理的请求头和频率控制
        reviews = []
        page = 0

        while len(reviews) < max_reviews:
            print(f"  正在采集第 {page + 1} 页...")
            time.sleep(CRAWL_DELAY)

            try:
                # 示例代码（实际使用需测试API可用性）:
                # url = f"https://club.jd.com/comment/productPageComments.action"
                # params = {
                #     "productId": product_id,
                #     "page": page,
                #     "pageSize": 10,
                #     "score": 0,  # 0=全部, 1=差评, 5=好评
                # }
                # response = requests.get(url, params=params,
                #                         headers=self.headers,
                #                         timeout=REQUEST_TIMEOUT)
                # data = response.json()
                # for item in data.get("comments", []):
                #     review = {
                #         "review_text": item.get("content", ""),
                #         "rating": item.get("score", 5),
                #         "platform": "京东",
                #         "timestamp": item.get("creationTime", ""),
                #         "user_id": str(item.get("id", "")),
                #         "product_name": "",
                #     }
                #     reviews.append(review)

                print(f"    (框架代码 - 实际使用时需配置平台API)")
                break

            except Exception as e:
                print(f"    采集出错: {e}")
                break

            page += 1

        return reviews[:max_reviews]

    # ═══════════════════════════════════════════════════════════════
    # 保存为CSV
    # ═══════════════════════════════════════════════════════════════

    def save_to_csv(self, reviews: List[Dict], filepath: str):
        """将评论列表保存为CSV文件"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        fieldnames = [
            "review_text", "rating", "platform",
            "timestamp", "user_id", "product_name"
        ]

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for review in reviews:
                writer.writerow({
                    k: review.get(k, "") for k in fieldnames
                })

        print(f"已保存 {len(reviews)} 条评论至 {filepath}")

    # ═══════════════════════════════════════════════════════════════
    # 创建测试数据
    # ═══════════════════════════════════════════════════════════════

    def create_sample_data(self, filepath: str = None) -> List[Dict]:
        """
        创建示例评论数据（用于测试和演示）

        包含各类情绪和有效性场景的典型评论
        """
        if filepath is None:
            filepath = os.path.join(DATA_DIR, "sample_reviews.csv")

        sample_reviews = [
            # 真诚好评
            {"review_text": "用了两周，续航确实给力，重度使用能撑一天半，充电也快，很满意", "rating": 5, "platform": "淘宝", "timestamp": "2026-08-01 14:30:00", "user_id": "u1001", "product_name": "某款智能手机"},
            {"review_text": "拍照效果很好，夜景模式很清晰，色彩还原度高，值得推荐", "rating": 5, "platform": "京东", "timestamp": "2026-08-02 09:15:00", "user_id": "u1002", "product_name": "某款智能手机"},
            {"review_text": "屏幕素质不错，120Hz刷新率很流畅，看视频体验很好", "rating": 5, "platform": "淘宝", "timestamp": "2026-08-03 16:20:00", "user_id": "u1003", "product_name": "某款智能手机"},

            # 反讽/阴阳怪气
            {"review_text": "这手机真是太好了，卡顿得让我学会了冥想，等待是一种修行", "rating": 5, "platform": "京东", "timestamp": "2026-08-04 10:00:00", "user_id": "u1004", "product_name": "某款智能手机"},
            {"review_text": "质量棒极了，买回来三天就坏了，省得我用太久，真环保", "rating": 5, "platform": "淘宝", "timestamp": "2026-08-05 11:30:00", "user_id": "u1005", "product_name": "某款智能手机"},
            {"review_text": "客服太热情了，热情到我想退货他们都拦着", "rating": 4, "platform": "淘宝", "timestamp": "2026-08-06 14:00:00", "user_id": "u1006", "product_name": "某款智能手机"},

            # 模板化好评（刷单）
            {"review_text": "好评！质量很好，物流很快，卖家态度好，下次还来！", "rating": 5, "platform": "淘宝", "timestamp": "2026-08-07 09:00:00", "user_id": "u1007", "product_name": "某款智能手机"},
            {"review_text": "好评！质量很好，物流很快，卖家态度好，下次还来！", "rating": 5, "platform": "淘宝", "timestamp": "2026-08-07 09:01:00", "user_id": "u1008", "product_name": "某款智能手机"},
            {"review_text": "很好很好很好很好很好", "rating": 5, "platform": "淘宝", "timestamp": "2026-08-08 10:00:00", "user_id": "u1009", "product_name": "某款智能手机"},

            # 明褒暗贬


            # 隐性抱怨
            {"review_text": "嗯……收到了，就这样吧", "rating": 3, "platform": "淘宝", "timestamp": "2026-08-10 14:00:00", "user_id": "u1012", "product_name": "某款智能手机"},
            {"review_text": "用了三天，目前还在用", "rating": 3, "platform": "京东", "timestamp": "2026-08-11 09:30:00", "user_id": "u1013", "product_name": "某款智能手机"},

            # 直接差评
            {"review_text": "质量太差了，用了一周就坏了，客服也不理人，千万别买", "rating": 1, "platform": "淘宝", "timestamp": "2026-08-11 16:00:00", "user_id": "u1014", "product_name": "某款智能手机"},
            {"review_text": "电池续航太差了，满电出门两小时就没电了，严重影响使用", "rating": 1, "platform": "京东", "timestamp": "2026-08-12 08:00:00", "user_id": "u1015", "product_name": "某款智能手机"},

            # 客观中性
            {"review_text": "音质还行，低音不错但高音有点闷，佩戴一般，续航中等", "rating": 3, "platform": "淘宝", "timestamp": "2026-08-12 10:00:00", "user_id": "u1016", "product_name": "某款智能手机"},
        ]

        self.save_to_csv(sample_reviews, filepath)
        return sample_reviews


if __name__ == "__main__":
    collector = DataCollector()
    # 创建示例数据
    reviews = collector.create_sample_data()
    print(f"\n示例数据已创建，共 {len(reviews)} 条评论")
    print("\n测试加载CSV:")
    loaded = collector.load_from_csv(
        os.path.join(DATA_DIR, "sample_reviews.csv")
    )
    print(f"加载了 {len(loaded)} 条评论")
