"""The same cost ceiling for synchronous API and CLI compatibility entry points."""
from __future__ import annotations

import json
import os
import uuid

from reviewagent import config
from reviewagent.llm import LLMNotConfigured
from reviewagent.model_budget import BudgetLedger, budget_client, representative_reviews
from reviewagent.review_data import normalize_reviews, result_succeeded


class AffordableAgent:
    def __init__(self):
        from reviewagent.sentiment_agent_core import ReviewAnalysisAgent
        if not config.is_llm_configured():
            raise LLMNotConfigured("未配置模型，请设置 DeepSeek API Key")
        model = "deepseek-flash" if config.MODEL in {"deepseek-chat", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"} else config.MODEL
        config.ensure_dirs()
        directory = config.DATA_DIR / "budgets"
        directory.mkdir(parents=True, exist_ok=True)
        self.receipt = directory / (uuid.uuid4().hex + ".json")
        def persist(snapshot):
            temporary = self.receipt.with_suffix(".tmp")
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, self.receipt)
        self.ledger = BudgetLedger(model, on_change=persist)
        self.agent = ReviewAnalysisAgent(model=model, base_url=config.BASE_URL, client=budget_client(self.ledger))
        self.model = model
        self.sampling = {}

    def batch_analyze(self, reviews, product_name="", *, on_result=None, should_cancel=None, existing_results=None):
        reviews = normalize_reviews(reviews)
        chosen, self.sampling = representative_reviews(reviews)
        indices = {review["review_id"]: index for index, review in enumerate(reviews)}
        similar = self.agent.similar_counts([review["review_text"] for review in reviews])
        def progress(index, result, done, total):
            if on_result:
                on_result(indices[result["review_id"]], result, done, len(reviews))
        results = self.agent.batch_analyze(chosen, product_name=product_name, on_result=progress,
                                          should_cancel=should_cancel, existing_results=existing_results,
                                          similar_counts_override=[similar[indices[r["review_id"]]] for r in chosen])
        by_id = {result["review_id"]: result for result in results}
        if self.ledger.exhausted:
            for result in by_id.values():
                if not result_succeeded(result):
                    result.update(status="pending", budget_deferred=True)
        full = [by_id.get(review["review_id"], {**review, "status": "pending", "final_analysis": {},
                                               "model_coverage": "not_selected_or_budget_limited"}) for review in reviews]
        self.sampling["modeled_count"] = sum(result_succeeded(result) for result in full)
        return full

    def generate_report(self, results, product_name=""):
        self.ledger.set_phase("insights")
        report = self.agent.generate_report(results, product_name=product_name)
        report.update(model_cost=self.ledger.snapshot(), model_coverage=self.sampling)
        if any(not result_succeeded(result) for result in results):
            report["status"] = "partial" if any(result_succeeded(result) for result in results) else "insufficient_data"
        return report

    def _call_llm(self, prompt, temperature=0.0):
        self.ledger.set_phase("insights")
        return self.agent._call_llm(prompt, temperature)
