# -*- coding: utf-8 -*-
"""分析历史与缓存管理（SQLite 存储）

历史记录写入 `data/reviewagent.db`，HTML 报告落在 `data/reports/`。
旧的 `data/history.json` 会在首次读取时自动迁移。
缓存清理只处理浏览器缓存、__pycache__ 与临时截图，绝不触碰历史、数据库和登录态。
"""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from reviewagent import config, store
from reviewagent.review_data import summarize_results

DATA_DIR = str(config.DATA_DIR)
REPORTS_DIR = str(config.REPORTS_DIR)
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")  # 旧格式位置，仅用于迁移/兼容

_CACHE_DIRS = [
    r"playwright-data\jd-dp-profile\Default\Cache",
    r"playwright-data\jd-dp-profile\Default\Code Cache",
    r"playwright-data\jd-dp-profile\Default\GPUCache",
    r"playwright-data\jd-dp-profile\Default\DawnGraphiteCache",
    r"playwright-data\jd-dp-profile\Default\DawnWebGPUCache",
    r"playwright-data\jd-dp-profile\Default\ShaderCache",
    r"playwright-data\jd-profile\Default\Cache",
    r"playwright-data\jd-profile\Default\Code Cache",
    r"playwright-data\jd-profile\Default\GPUCache",
    r"playwright-data\jd-profile\Default\DawnGraphiteCache",
    r"playwright-data\jd-profile\Default\DawnWebGPUCache",
    r"playwright-data\jd-profile\Default\ShaderCache",
    r"playwright-data\Default\Cache",
    r"playwright-data\Default\Code Cache",
    r"playwright-data\Default\GPUCache",
    r"playwright-data\Default\DawnGraphiteCache",
    r"playwright-data\Default\DawnWebGPUCache",
    r"playwright-data\GrShaderCache",
    r"playwright-data\ShaderCache",
    r"playwright-data\GPUPersistentCache",
    r"playwright-data\segmentation_platform",
    r"playwright-data\jd-dp-profile\optimization_guide_model_store",
    r"playwright-data\jd-dp-profile\Safe Browsing",
    r"playwright-data\jd-dp-profile\component_crx_cache",
    r"playwright-data\jd-dp-profile\WasmTtsEngine",
    r"playwright-data\jd-dp-profile\BrowserMetrics",
    r"playwright-data\jd-dp-profile\ActorSafetyLists",
    r"playwright-data\jd-dp-profile\hyphen-data",
    r"playwright-data\jd-dp-profile\ZxcvbnData",
    r"playwright-data\jd-dp-profile\CertificateRevocation",
    r"playwright-data\jd-dp-profile\OptimizationHints",
    r"playwright-data\jd-profile\optimization_guide_model_store",
    r"playwright-data\jd-profile\BrowserMetrics",
    r"playwright-data\jd-profile\CertificateRevocation",
    r"playwright-data\Crashpad",
    r"playwright-data\extensions_crx_cache",
    r"debug",
    r".llm_cache",
]


# ── 历史记录 ──────────────────────────────────────────────────

def load_history() -> List[Dict[str, Any]]:
    """按时间倒序返回全部历史记录。"""
    return store.list_history()


def save_history_record(
    source: str,
    platform: str,
    url: str,
    product_name: str,
    reviews: List[Dict],
    results: List[Dict],
    report: Dict,
    trust_report: Dict,
) -> Optional[str]:
    """保存一次完整分析记录，返回记录 ID。"""
    config.ensure_dirs()
    record_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{int(datetime.now().timestamp() * 1000) % 1000:03d}"

    stats = summarize_results(results)
    total = len(results)
    sarcastic = stats["sarcastic_count"]
    suspicious = stats["suspicious_count"]
    avg_trust = stats["avg_trust_score"]
    sentiment_dist = stats["sentiment_distribution"]

    methods: Dict[str, int] = {}
    for r in reviews:
        m = r.get("extraction_method", "unknown")
        methods[m] = methods.get(m, 0) + 1

    # 自动生成 HTML 报告（失败不影响记录保存）
    html_path = None
    try:
        from reviewagent.report_generator import HTMLReportGenerator
        gen = HTMLReportGenerator()
        tmp_html = gen.generate(results=results, report=report, product_name=product_name or "产品")
        if tmp_html and os.path.exists(tmp_html):
            dest = os.path.join(REPORTS_DIR, f"{record_id}.html")
            shutil.copy2(tmp_html, dest)
            html_path = dest
    except Exception:
        pass

    record = {
        "id": record_id,
        "timestamp": datetime.now().isoformat(),
        "timestamp_display": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "platform": platform,
        "url": url,
        "product_name": product_name,
        "review_count": total,
        "sarcastic_count": sarcastic,
        "suspicious_count": suspicious,
        "avg_trust_score": avg_trust,
        "statistics": stats,
        "reviews": reviews,
        "sentiment_distribution": sentiment_dist,
        "extraction_methods": methods,
        "report": report,
        "trust_report": trust_report,
        "results": results,
        "html_report_path": html_path,
    }
    store.save_history_record(record)
    return record_id


def delete_record(record_id: str) -> bool:
    """删除一条历史记录及其 HTML 报告。"""
    if not store.delete_history(record_id):
        return False
    html_path = os.path.join(REPORTS_DIR, f"{record_id}.html")
    if os.path.exists(html_path):
        try:
            os.remove(html_path)
        except OSError:
            pass
    return True


def clear_all_history() -> int:
    """清空全部历史记录与已生成的报告文件。"""
    count = store.clear_history()
    if os.path.isdir(REPORTS_DIR):
        for f in os.listdir(REPORTS_DIR):
            try:
                os.remove(os.path.join(REPORTS_DIR, f))
            except OSError:
                pass
    return count


# ── 缓存管理 ──────────────────────────────────────────────────

def _dir_size(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def get_cache_size() -> int:
    """返回可安全清理的缓存字节数。"""
    total = 0
    home = str(config.HOME_DIR)
    for d in _CACHE_DIRS:
        full = os.path.join(home, d)
        if os.path.isdir(full):
            total += _dir_size(full)
    for root, dirs, _ in os.walk(home):
        if any(part in root for part in ("venv", ".venv", ".git", "data", "output")):
            continue
        if "__pycache__" in dirs:
            total += _dir_size(os.path.join(root, "__pycache__"))
    shots = os.path.join(tempfile.gettempdir(), "jd_screenshots")
    if os.path.isdir(shots):
        total += _dir_size(shots)
    return total


def clear_cache() -> int:
    """清理缓存，返回释放的字节数。不会触碰历史、数据库与登录态。"""
    freed = 0
    home = str(config.HOME_DIR)
    for d in _CACHE_DIRS:
        full = os.path.join(home, d)
        if os.path.isdir(full):
            try:
                freed += _dir_size(full)
                shutil.rmtree(full)
            except OSError:
                pass
    for root, dirs, _ in os.walk(home):
        if any(part in root for part in ("venv", ".venv", ".git", "data", "output")):
            continue
        if "__pycache__" in dirs:
            d = os.path.join(root, "__pycache__")
            try:
                freed += _dir_size(d)
                shutil.rmtree(d)
            except OSError:
                pass
    shots = os.path.join(tempfile.gettempdir(), "jd_screenshots")
    if os.path.isdir(shots):
        try:
            freed += _dir_size(shots)
            shutil.rmtree(shots)
        except OSError:
            pass
    return freed
