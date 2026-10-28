"""平台受阻分类：京东频控、天猫精简页、京东接口限流，全部离线复现。"""
import pytest

from reviewagent import browser_collection as bc
from reviewagent import public_collection as pc


class FakeDriver:
    def __init__(self, url, script_result="ready"):
        self.current_url = url
        self.script_result = script_result
        self.scripts = []

    def execute_script(self, script, *args):
        self.scripts.append((script, args))
        if isinstance(self.script_result, dict) and "scrollHeight" in script:
            return self.script_result
        if isinstance(self.script_result, dict):
            return self.script_result.get("state", "ready")
        return self.script_result


def test_jd_frequent_control_host_is_rate_limited():
    driver = FakeDriver("https://pc-frequent-pro.pf.jd.com/")
    assert bc._page_state(driver, "jd") == "rate_limited"


def test_jd_normal_host_is_not_mistaken_for_block():
    driver = FakeDriver("https://item.jd.com/100394190476.html")
    assert bc._page_state(driver, "jd") == "ready"


def test_purchase_only_page_is_degraded():
    evidence_snapshot = {"len": 240, "hasReviews": False, "height": 979}
    assert bc._degraded_page(evidence_snapshot) is True


def test_normal_page_is_not_degraded():
    assert bc._degraded_page({"len": 2600, "hasReviews": True, "height": 5200}) is False
    assert bc._degraded_page(None) is False


def test_thin_page_raises_degraded_instead_of_empty_success(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(bc.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(bc, "_wait", lambda seconds, cancelled: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(bc, "_await_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(bc, "_scroll_comments", lambda driver: None)
    driver = FakeDriver("https://detail.tmall.com/item.htm?id=1",
                        script_result={"state": "ready", "len": 240, "hasReviews": False, "height": 979})
    events = []
    with pytest.raises(bc.CollectionPaused) as excinfo:
        bc._wait_for_comment_section(driver, "taobao", "https://detail.tmall.com/item.htm?id=1", lambda: False,
                                     lambda status, message: events.append(status))
    assert excinfo.value.code == "degraded_page"


class FakeResponse:
    status_code = 200
    encoding = "utf-8"

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, size):
        yield self.body


class FakeSession:
    trust_env = False

    def __init__(self, body):
        self.headers = {}
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        return FakeResponse(self.body)


def test_jd_api_block_message_raises_rate_limited(monkeypatch):
    monkeypatch.setattr(pc.requests, "Session", lambda: FakeSession("活动太火爆，请稍微再试".encode()))
    with pytest.raises(bc.CollectionPaused) as excinfo:
        pc.public_reviews({"platform": "jd", "url": "https://item.jd.com/100394190476.html"}, 10, lambda: False)
    assert excinfo.value.code == "rate_limited"
