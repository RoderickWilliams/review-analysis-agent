"""
History Manager - persistent analysis history and safe cache management.
Stores records in data/history.json, HTML reports in data/reports/.
Cache cleanup never touches history, cookies, or login state.
"""
import os
import sys
import json
import time
import shutil
import tempfile
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")


def _ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)


def load_history() -> List[Dict[str, Any]]:
    _ensure_dirs()
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(records: List[Dict[str, Any]]):
    _ensure_dirs()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


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
    """Save a complete analysis record. Returns record ID."""
    _ensure_dirs()
    record_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"

    total = len(results)
    sarcastic = sum(1 for r in results if r.get("sentiment_analysis", {}).get("is_sarcastic"))
    suspicious = sum(
        1 for r in results
        if r.get("final_analysis", {}).get("final_validity") in ("suspicious", "fake")
    )
    avg_trust = (
        sum(r.get("final_analysis", {}).get("trust_score", 50) for r in results) / total
        if total else 0
    )

    sentiment_dist: Dict[str, int] = {}
    for r in results:
        label = r.get("sentiment_analysis", {}).get("sentiment_label", "unknown")
        sentiment_dist[label] = sentiment_dist.get(label, 0) + 1

    methods: Dict[str, int] = {}
    for r in reviews:
        m = r.get("extraction_method", "unknown")
        methods[m] = methods.get(m, 0) + 1

    # Auto-generate HTML report
    html_path = None
    try:
        from report_generator import HTMLReportGenerator
        gen = HTMLReportGenerator()
        tmp_html = gen.generate(
            results=results, report=report,
            product_name=product_name or "产品",
        )
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
        "avg_trust_score": round(avg_trust, 1),
        "sentiment_distribution": sentiment_dist,
        "extraction_methods": methods,
        "report": report,
        "trust_report": trust_report,
        "results": results,
        "html_report_path": html_path,
    }

    records = load_history()
    records.insert(0, record)
    _save_history(records)
    return record_id


def delete_record(record_id: str) -> bool:
    records = load_history()
    new_records = [r for r in records if r.get("id") != record_id]
    if len(new_records) < len(records):
        _save_history(new_records)
        html_path = os.path.join(REPORTS_DIR, f"{record_id}.html")
        if os.path.exists(html_path):
            try:
                os.remove(html_path)
            except Exception:
                pass
        return True
    return False


def clear_all_history() -> int:
    records = load_history()
    count = len(records)
    _save_history([])
    if os.path.isdir(REPORTS_DIR):
        for f in os.listdir(REPORTS_DIR):
            try:
                os.remove(os.path.join(REPORTS_DIR, f))
            except Exception:
                pass
    return count


# ── Cache management ──────────────────────────────────────────

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
    """Bytes that can be safely freed."""
    total = 0
    for d in _CACHE_DIRS:
        full = os.path.join(PROJECT_ROOT, d)
        if os.path.isdir(full):
            total += _dir_size(full)
    # __pycache__
    for root, dirs, _ in os.walk(PROJECT_ROOT):
        if "venv" in root or ".git" in root or "data" in root:
            continue
        if "__pycache__" in dirs:
            total += _dir_size(os.path.join(root, "__pycache__"))
    # temp screenshots
    shots = os.path.join(tempfile.gettempdir(), "jd_screenshots")
    if os.path.isdir(shots):
        total += _dir_size(shots)
    return total


def clear_cache() -> int:
    """Safely clear caches. Returns bytes freed. Never touches history/cookies."""
    freed = 0
    for d in _CACHE_DIRS:
        full = os.path.join(PROJECT_ROOT, d)
        if os.path.isdir(full):
            try:
                freed += _dir_size(full)
                shutil.rmtree(full)
            except Exception:
                pass
    for root, dirs, _ in os.walk(PROJECT_ROOT):
        if "venv" in root or ".git" in root or "data" in root:
            continue
        if "__pycache__" in dirs:
            d = os.path.join(root, "__pycache__")
            try:
                freed += _dir_size(d)
                shutil.rmtree(d)
            except Exception:
                pass
    shots = os.path.join(tempfile.gettempdir(), "jd_screenshots")
    if os.path.isdir(shots):
        try:
            freed += _dir_size(shots)
            shutil.rmtree(shots)
        except Exception:
            pass
    return freed
