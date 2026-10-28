"""Persisted request reservations using conservative official DeepSeek peak prices."""
from __future__ import annotations

import json
import threading
from collections import defaultdict, deque
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlsplit

PRICING_SOURCE = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
PRICING_DATE = "2026-10-27"
OFFICIAL_DEEPSEEK_PRICES = {"deepseek-flash": (Decimal("2"), Decimal("8")),
          "deepseek-v4-pro": (Decimal("9"), Decimal("27"))}
PRICES = dict(OFFICIAL_DEEPSEEK_PRICES)


class BudgetExceeded(ValueError):
    pass


class BudgetLedger:
    def __init__(self, model, previous=None, on_change=None):
        if model not in PRICES:
            raise ValueError("当前模型没有已确认的预算价格，请使用 deepseek-flash 或 deepseek-v4-pro")
        self.model = model
        self.rates = PRICES[model]
        self.entries = [dict(entry) for entry in (previous or {}).get("entries", [])]
        # A request interrupted before settlement may already have been billed.
        for entry in self.entries:
            if entry.get("state") == "reserved":
                entry["state"] = "uncertain"
        self.phase = "reviews"
        self.exhausted = False
        self.lock = threading.RLock()
        self.on_change = on_change

    def spent(self):
        return sum((Decimal(str(entry["accounted_cny"])) for entry in self.entries), Decimal("0"))

    def snapshot(self):
        with self.lock:
            return {"currency": "CNY", "target_cny": 1, "hard_limit_cny": 1.5, "request_stop_cny": 1.4,
                    "accounted_cny": float(self.spent()), "has_uncertain_cost": any(e["state"] in {"reserved", "uncertain"} for e in self.entries),
                    "pricing_date": PRICING_DATE, "pricing_source": PRICING_SOURCE if self.model.startswith("deepseek") else "user_confirmed_cny_rates",
                    "pricing_basis": "高峰、输入未命中缓存的保守估价；最终以供应商账单为准",
                    "input_cny_per_million": float(self.rates[0]), "output_cny_per_million": float(self.rates[1]),
                    "remaining_input_tokens_only": max(0, int((Decimal("1.40") - self.spent()) * 1_000_000 / self.rates[0])),
                    "remaining_output_tokens_only": max(0, int((Decimal("1.40") - self.spent()) * 1_000_000 / self.rates[1])),
                    "entries": [dict(e) for e in self.entries]}

    def _publish(self):
        if self.on_change:
            self.on_change(self.snapshot())

    def set_phase(self, phase):
        with self.lock:
            self.phase, self.exhausted = phase, False

    def output_allowance(self, messages, desired=2048):
        with self.lock:
            input_bound = len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 1024
            limit = Decimal("0.80") if self.phase == "reviews" else Decimal("1.40")
            remaining = limit - self.spent() - self.rates[0] * input_bound / 1_000_000
            allowance = min(desired, max(0, int(remaining * 1_000_000 / self.rates[1])))
            if allowance < 256:
                self.exhausted = True
                raise BudgetExceeded("本次分析的剩余预算不足，已停止模型生成；评论及已有结果保留")
            return allowance

    def reserve(self, messages, output_tokens):
        with self.lock:
            if any(entry.get("state") == "usage_overrun" for entry in self.entries):
                self.exhausted = True
                raise BudgetExceeded("供应商用量超过预留值，已停止后续模型请求，请核对账单")
            # UTF-8 byte length plus framing is an intentionally loose token bound.
            input_bound = len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 1024
            input_price, output_price = self.rates
            reservation = (input_price * input_bound + output_price * output_tokens) / 1_000_000
            phase_limit = Decimal("0.80") if self.phase == "reviews" else Decimal("1.40")
            if self.spent() + reservation > phase_limit:
                self.exhausted = True
                raise BudgetExceeded("已到达本阶段模型预算，剩余原文保留并采用代表样本分析")
            entry = {"model": self.model, "phase": self.phase, "state": "reserved",
                     "input_price": str(input_price), "output_price": str(output_price),
                     "reserved_cny": str(reservation), "accounted_cny": str(reservation),
                     "input_bound": input_bound, "output_limit": output_tokens,
                     "started_at": datetime.now().astimezone().isoformat()}
            self.entries.append(entry)
            # Persist the reservation before any paid network operation.
            self._publish()
            return len(self.entries) - 1

    def settle(self, index, usage=None, *, unbilled=False):
        with self.lock:
            entry = self.entries[index]
            prompt = getattr(usage, "prompt_tokens", None)
            completion = getattr(usage, "completion_tokens", None)
            if unbilled:
                entry.update(state="unbilled_error", accounted_cny="0")
            elif all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (prompt, completion)):
                input_price, output_price = Decimal(entry["input_price"]), Decimal(entry["output_price"])
                cost = (input_price * prompt + output_price * completion) / 1_000_000
                entry.update(state="usage_estimated", accounted_cny=str(cost), prompt_tokens=prompt, completion_tokens=completion)
                if cost > Decimal(entry["reserved_cny"]):
                    entry["state"] = "usage_overrun"
                    self.exhausted = True
            else:
                entry["state"] = "uncertain"
            self._publish()


class BudgetClient:
    def __init__(self, client, ledger):
        self.client, self.ledger = client, ledger
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        output_tokens = self.ledger.output_allowance(kwargs.get("messages", []))
        kwargs.update(max_tokens=output_tokens)
        if self.ledger.model.startswith("deepseek"):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        elif self.ledger.model.startswith(("gpt-5", "o1", "o3", "o4")):
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
            kwargs.pop("temperature", None)
        ticket = self.ledger.reserve(kwargs.get("messages", []), output_tokens)
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            self.ledger.settle(ticket, unbilled=getattr(exc, "status_code", None) in {400, 401, 402, 403, 404, 422, 429})
            raise
        self.ledger.settle(ticket, getattr(response, "usage", None))
        return response


def budget_client(ledger):
    from reviewagent.llm import RotatingClient
    from reviewagent import config
    parsed = urlsplit(config.BASE_URL or "")
    from reviewagent.model_settings import permitted_base
    if parsed.scheme != "https" or not permitted_base(config.BASE_URL or "") or parsed.username or parsed.password:
        raise ValueError("请先在工作台设置中验证供应商与模型接口")
    if not config.API_KEYS:
        raise ValueError("尚未配置模型 API Key")
    # Each channel attempt reserves separately; SDK retries remain disabled.
    return RotatingClient(config.API_KEYS, config.BASE_URL, config.LLM_TIMEOUT, 0, ledger=ledger)


def representative_reviews(reviews, limit=120):
    """Round-robin across platform, group and rating; deduplicate only for modeling."""
    buckets, seen = defaultdict(deque), set()
    for review in reviews:
        group = review.get("group_id") or review.get("source_url") or "manual"
        identity = (review.get("platform"), group, "".join(review["review_text"].split()).casefold())
        if identity in seen:
            continue
        seen.add(identity)
        buckets[(review.get("platform"), group, review.get("rating"))].append(review)
    selected = []
    while len(selected) < limit and any(buckets.values()):
        for bucket in buckets.values():
            if bucket and len(selected) < limit:
                selected.append(bucket.popleft())
    return selected, {"local_count": len(reviews), "unique_text_count": len(seen), "selected_count": len(selected),
                      "method": "platform_group_rating_round_robin", "selected_ids": [r["review_id"] for r in selected]}
