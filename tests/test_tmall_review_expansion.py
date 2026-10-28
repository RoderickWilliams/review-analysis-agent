"""Contracts for review expansion: trusted clicks and the page's own rate API."""
from reviewagent import browser_collection as bc


class FakeDriver:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.clicks = []

    def execute_script(self, script, *args):
        self.calls.append(args)
        return self.results.pop(0) if self.results else None

    def click_at(self, x, y):
        self.clicks.append((x, y))


class ScriptOnlyDriver:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute_script(self, script, *args):
        self.calls.append(args)
        return self.results.pop(0) if self.results else None


def test_expand_entry_clicks_the_scrolled_point():
    driver = FakeDriver([{"x": 120, "y": 240, "text": "查看全部评价", "tag": "DIV"}])
    assert bc._open_comments(driver, all_only=True) is True
    assert driver.clicks == [(120, 240)]


def test_expand_entry_without_trusted_input_uses_script_click():
    driver = ScriptOnlyDriver([{"x": 5, "y": 6}, True])
    assert bc._open_comments(driver, all_only=True) is True
    assert len(driver.calls) == 2


def test_expand_entry_returns_false_when_nothing_matches():
    driver = FakeDriver([None])
    assert bc._open_comments(driver) is False
    assert driver.clicks == []


def test_rate_paging_reads_normal_then_folded_reviews():
    driver = FakeDriver([
        {"rows": [{"id": "a", "feedback": "好评一条"}], "total": 11},
        {"rows": [], "total": 11},
        {"rows": [{"id": "b", "feedback": "默认好评"}], "total": 2},
        {"rows": [], "total": 2},
    ])
    rows, ok = bc._tmall_rate_rows(driver, "568742960823", 50, lambda: False)
    assert ok is True
    assert [row["id"] for row in rows] == ["a", "b"]


def test_rate_paging_reports_unavailable_library():
    driver = FakeDriver([None])
    rows, ok = bc._tmall_rate_rows(driver, "568742960823", 50, lambda: False)
    assert rows == []
    assert ok is False


def test_rate_paging_stops_at_limit():
    driver = FakeDriver([
        {"rows": [{"id": "a"}, {"id": "b"}], "total": 11},
        {"rows": [{"id": "c"}], "total": 11},
    ])
    rows, ok = bc._tmall_rate_rows(driver, "568742960823", 2, lambda: False)
    assert ok is True
    assert len(rows) == 2


def test_review_batch_carries_page_facts():
    batch = bc.ReviewBatch([{"review_text": "一条"}], {"displayed": 33, "folded": 22})
    assert len(batch) == 1
    assert batch.facts["folded"] == 22
