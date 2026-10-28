"""没有显式选择时，只采集当前对象；用户补充的链接带 user_supplied 标记才采集。"""
from reviewagent.collection import _sources


def make_analysis(candidates, selected=None):
    request = {"tier": "standard", "platforms": ["jd"]}
    if selected is not None:
        request["selected_urls"] = selected
    return {"request": request,
            "object": {"platform": "jd", "url": "https://item.jd.com/1.html", "status": "needs_capture"},
            "candidates": candidates}


def test_candidates_are_not_collected_without_selection():
    analysis = make_analysis([{"platform": "jd", "url": "https://item.jd.com/2.html"}])
    assert [item["url"] for item in _sources(analysis)] == ["https://item.jd.com/1.html"]


def test_user_supplied_links_are_collected():
    analysis = make_analysis([{"platform": "jd", "url": "https://item.jd.com/3.html", "user_supplied": True}])
    urls = [item["url"] for item in _sources(analysis)]
    assert "https://item.jd.com/3.html" in urls
    assert len(urls) == 2


def test_explicit_selection_still_uses_selected_links():
    analysis = make_analysis([{"platform": "jd", "url": "https://item.jd.com/4.html"}],
                             selected=["https://item.jd.com/4.html"])
    assert [item["url"] for item in _sources(analysis)] == ["https://item.jd.com/4.html"]

def test_xhslink_cn_is_recognized_as_xhs():
    from reviewagent.browser_collection import _allowed_url
    from reviewagent.object_resolver import detect_platform

    assert detect_platform("https://xhslink.cn/o/7zUsGv1lB2l") == "xhs"
    assert _allowed_url("https://xhslink.cn/o/7zUsGv1lB2l", "xhs")
