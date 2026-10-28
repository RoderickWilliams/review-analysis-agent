"""Conservative identities: title similarity and a shared SPU never authorize merging."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from reviewagent.review_data import summarize_results


def normalized(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip().casefold()


def identity(obj):
    specs = obj.get("key_specs") or {}
    if not isinstance(specs, dict):
        specs = {}
    return {"brand": normalized(obj.get("brand")), "model": normalized(obj.get("model") or obj.get("model_number") or obj.get("mpn")),
            "key_specs": {normalized(k): normalized(v) for k, v in specs.items() if normalized(k) and normalized(v)}}


def compare_identity(left, right):
    a, b = identity(left), identity(right)
    missing = [name for name in ("brand", "model", "key_specs") if not a[name] or not b[name]]
    if left.get("specs_confirmed") is False or right.get("specs_confirmed") is False:
        missing.append("key_specs_confirmation")
    if a["brand"] and b["brand"] and a["brand"] != b["brand"]:
        return {"level": "competitor", "merge_allowed": False, "reason": "品牌不同，单独分析并比较", "missing": missing}
    if a["model"] and b["model"] and a["model"] != b["model"]:
        return {"level": "similar", "merge_allowed": False, "reason": "型号不同，单独分析并比较", "missing": missing}
    if a["key_specs"] and b["key_specs"] and a["key_specs"] != b["key_specs"]:
        return {"level": "variant", "merge_allowed": False, "reason": "关键规格不同，单独分析并比较", "missing": missing}
    if missing:
        return {"level": "uncertain", "merge_allowed": False, "reason": "品牌、型号或关键规格尚未核对，不能自动合并", "missing": missing}
    return {"level": "exact", "merge_allowed": True, "reason": "品牌、型号和全部已声明关键规格一致", "missing": []}


def assign_groups(analysis):
    sources = [analysis.get("object") or {}] + list(analysis.get("candidates") or [])
    by_url = {source.get("url") or source.get("source_url"): source for source in sources if source.get("url") or source.get("source_url")}
    overrides = analysis.get("source_identities") or {}
    for source in sources:
        url = source.get("url") or source.get("source_url") or ""
        if url in overrides:
            source.update(overrides[url])
    for url, values in overrides.items():
        if url and url not in by_url:
            by_url[url] = values
    labels = {"exact": "同款", "variant": "不同规格", "similar": "近似款", "competitor": "竞品", "uncertain": "不确定"}
    for candidate in analysis.get("candidates", []):
        comparison = compare_identity(analysis.get("object") or {}, candidate)
        candidate.update(match_level=comparison["level"], match_label=labels[comparison["level"]],
                         merge_allowed=comparison["merge_allowed"], identity_missing=comparison["missing"])
    if analysis.get("match_summary") is not None:
        for level in labels:
            analysis["match_summary"][level] = sum(c.get("match_level") == level for c in analysis.get("candidates", []))
    groups = {}
    for review in analysis.get("reviews", []):
        url = review.get("source_url") or ""
        source = by_url.get(url, analysis.get("object") or {}) if not url else by_url.get(url, {})
        base = identity({**source, **{key: review[key] for key in ("brand", "model", "key_specs") if review.get(key)}})
        sku = normalized(review.get("sku"))
        # Site-wide reviews may include other SKUs even on a fully known product page.
        if review.get("key_specs"):
            specs = identity(review)["key_specs"]
        elif source.get("reviews_scope") == "selected_spec":
            specs = base["key_specs"]
        elif sku and base["key_specs"] and all(value in sku for value in base["key_specs"].values()):
            specs = base["key_specs"]
        elif sku:
            specs = {"评论所选规格": sku}
        else:
            specs = {}
        confirmed = bool(base["brand"] and base["model"] and base["key_specs"] and specs
                         and (review.get("key_specs") or specs == base["key_specs"])
                         and (review.get("key_specs") or source.get("specs_confirmed") is not False))
        key = {"brand": base["brand"], "model": base["model"], "specs": specs}
        if not confirmed:
            key.update(source=url or "manual", platform=review.get("platform"),
                       product=normalized(review.get("product_name")), sku=sku)
        group_id = "group_" + hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        review["group_id"] = group_id
        review["analysis_context"] = json.dumps({"product": review.get("product_name") or source.get("title") or analysis.get("input"),
                                                  "brand": base["brand"], "model": base["model"], "specs": specs,
                                                  "group_id": group_id}, ensure_ascii=False, sort_keys=True)
        group = groups.setdefault(group_id, {"group_id": group_id, "brand": base["brand"], "model": base["model"],
                                  "key_specs": specs, "status": "confirmed" if confirmed else "pending_identity",
                                  "title": review.get("product_name") or source.get("title") or analysis.get("input", "商品"),
                                  "spec_label": review.get("sku") or " / ".join(specs.values()) or "规格待确认",
                                  "review_ids": [], "source_urls": [], "platforms": []})
        group["review_ids"].append(review["review_id"])
        if url and url not in group["source_urls"]:
            group["source_urls"].append(url)
        if review.get("platform") not in group["platforms"]:
            group["platforms"].append(review.get("platform"))
    results = {result.get("review_id"): result for result in analysis.get("results", [])}
    for group in groups.values():
        group["statistics"] = summarize_results([results[rid] for rid in group["review_ids"] if rid in results])
        group["statistics"]["pending_count"] += sum(rid not in results for rid in group["review_ids"])
        group["review_count"] = len(group["review_ids"])
    analysis["groups"] = list(groups.values())
    analysis.setdefault("request", {})["reviews"] = analysis.get("reviews", [])
    return analysis["groups"]
