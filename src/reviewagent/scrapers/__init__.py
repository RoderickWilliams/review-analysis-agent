# -*- coding: utf-8 -*-
"""
多平台评论爬虫模块 (scrapers)

提供淘宝/天猫、京东等平台的评论抓取与聚合能力。

主要接口::

    from reviewagent.scrapers import MultiPlatformScraper

    scraper = MultiPlatformScraper(delay=2.0)
    reviews = scraper.scrape_product("https://item.jd.com/100012043978.html")

参考: https://github.com/MohsinCell/NLP-Review-Authenticity-Analysis
"""

from reviewagent.scrapers.base_scraper import BaseScraper
from reviewagent.scrapers.jd_scraper import JDScraper
from reviewagent.scrapers.multi_platform import MultiPlatformScraper
from reviewagent.scrapers.taobao_scraper import TaobaoScraper
from reviewagent.scrapers.taobao_playwright_scraper import TaobaoPlaywrightScraper

__all__ = [
    "MultiPlatformScraper",
    "BaseScraper",
    "TaobaoScraper",
    "TaobaoPlaywrightScraper",
    "JDScraper",
]

__version__ = "1.0.0"
