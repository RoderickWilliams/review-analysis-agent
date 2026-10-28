"""模板化/疑似刷评语料库：按正文去重追加，并作为提示词参考样本。"""
from reviewagent import config, review_corpus


def test_append_flagged_dedupes_by_text(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    reviews = [{"review_id": "r1", "review_text": "品质保障，性价比高，多次购买", "rating": 5, "platform": "jd"}]
    results = [{"review_id": "r1", "final_analysis": {"final_validity": "suspicious"}}]
    assert review_corpus.append_flagged(reviews, results) == 1
    assert review_corpus.append_flagged(reviews, results) == 0
    rows = review_corpus._read_rows()
    assert len(rows) == 1
    assert rows[0]["verdict"] == "suspicious"


def test_authentic_reviews_are_not_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    reviews = [{"review_id": "r1", "review_text": "用了一个月，缝线开了", "rating": 2, "platform": "jd"}]
    results = [{"review_id": "r1", "final_analysis": {"final_validity": "authentic"}}]
    assert review_corpus.append_flagged(reviews, results) == 0


def test_format_examples_lists_saved_reviews(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    for index in range(8):
        review_corpus.append_flagged(
            [{"review_id": "r%d" % index, "review_text": "模板评论第%d条：质量很好物流很快" % index,
              "rating": 5, "platform": "jd"}],
            [{"review_id": "r%d" % index, "final_analysis": {"final_validity": "fake"}}])
    text = review_corpus.format_examples(limit=5)
    assert "参考样本" in text
    assert text.count("模板评论第") == 5
