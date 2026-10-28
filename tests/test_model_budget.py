"""Cost guards use fake responses and never send API requests."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from reviewagent.model_budget import BudgetClient, BudgetExceeded, BudgetLedger, representative_reviews


def _client(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_reservation_is_persisted_before_request_and_settled_from_usage():
    saved = []
    ledger = BudgetLedger("deepseek-flash", on_change=saved.append)
    def create(**kwargs):
        assert saved[-1]["entries"][-1]["state"] == "reserved"
        assert kwargs["max_tokens"] == 2048
        assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=100))
    client = BudgetClient(_client(create), ledger)
    client.chat.completions.create(model="deepseek-flash", messages=[{"role": "user", "content": "fixture"}])
    assert ledger.spent() == Decimal("0.0028")
    assert saved[-1]["entries"][-1]["state"] == "usage_estimated"


def test_request_over_remaining_budget_never_reaches_provider():
    ledger = BudgetLedger("deepseek-flash", {"entries": [{"state": "uncertain", "accounted_cny": "1.399"}]})
    ledger.set_phase("insights")
    calls = []
    client = BudgetClient(_client(lambda **kwargs: calls.append(kwargs)), ledger)
    with pytest.raises(BudgetExceeded):
        client.chat.completions.create(messages=[])
    assert calls == []


def test_timeout_keeps_full_reservation_and_does_not_retry():
    ledger = BudgetLedger("deepseek-flash")
    calls = []
    def timeout(**kwargs):
        calls.append(True)
        raise TimeoutError("fixture")
    with pytest.raises(TimeoutError):
        BudgetClient(_client(timeout), ledger).chat.completions.create(messages=[])
    assert calls == [True]
    assert ledger.snapshot()["has_uncertain_cost"]
    assert ledger.entries[0]["accounted_cny"] == ledger.entries[0]["reserved_cny"]


def test_crashed_reservation_is_not_refunded_on_resume():
    ledger = BudgetLedger("deepseek-flash")
    ledger.reserve([], 2048)
    resumed = BudgetLedger("deepseek-flash", ledger.snapshot())
    assert resumed.spent() == ledger.spent()
    assert resumed.entries[0]["state"] == "uncertain"


def test_review_phase_leaves_budget_for_report():
    ledger = BudgetLedger("deepseek-flash", {"entries": [{"state": "uncertain", "accounted_cny": "0.79"}]})
    with pytest.raises(BudgetExceeded):
        ledger.reserve([], 2048)
    ledger.set_phase("insights")
    ledger.reserve([], 2048)
    assert ledger.spent() < Decimal("1.4")


def test_unknown_model_has_no_implicit_price():
    with pytest.raises(ValueError):
        BudgetLedger("unknown-priced-model")


def test_provider_usage_overrun_blocks_all_later_phases():
    ledger = BudgetLedger("deepseek-flash")
    ticket = ledger.reserve([], 2048)
    ledger.settle(ticket, SimpleNamespace(prompt_tokens=10, completion_tokens=300000))
    ledger.set_phase("insights")
    with pytest.raises(BudgetExceeded):
        ledger.reserve([], 2048)


def test_sampling_retains_platform_and_rating_diversity_without_dropping_raw_data():
    reviews = [{"review_id": str(i), "review_text": text, "platform": platform, "rating": rating, "group_id": "same"}
               for i, (text, platform, rating) in enumerate([
                   ("相同评论", "jd", 5), ("相同评论", "jd", 5),
                   ("相同评论", "taobao", 5), ("具体问题", "jd", 1), ("未知评分内容", "xhs", None)])]
    selected, metadata = representative_reviews(reviews)
    assert len(reviews) == 5
    assert len(selected) == 4
    assert {review["platform"] for review in selected} == {"jd", "taobao", "xhs"}
    assert metadata["local_count"] == 5


def test_key_failover_has_a_separate_reservation_for_each_attempt(monkeypatch):
    from reviewagent import config
    from reviewagent.model_budget import budget_client
    calls = []
    def fake_openai(api_key, **kwargs):
        assert kwargs["max_retries"] == 0
        def create(**request):
            calls.append(api_key)
            if api_key == "fixture-channel-a":
                error = RuntimeError("fixture quota")
                error.status_code = 429
                raise error
            return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10))
        return _client(create)
    monkeypatch.setattr("openai.OpenAI", fake_openai)
    monkeypatch.setattr(config, "API_KEYS", ["fixture-channel-a", "fixture-channel-b"])
    monkeypatch.setattr(config, "BASE_URL", "https://api.deepseek.com")
    ledger = BudgetLedger("deepseek-flash")
    budget_client(ledger).chat.completions.create(model="deepseek-flash", messages=[])
    assert calls == ["fixture-channel-a", "fixture-channel-b"]
    assert len(ledger.entries) == 2
    assert ledger.entries[0]["state"] == "unbilled_error"
    assert ledger.entries[1]["state"] == "usage_estimated"
    assert ledger.spent() == Decimal("0.00028")
