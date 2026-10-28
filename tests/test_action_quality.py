"""运营动作：优先级排序，以及把工厂侧事项改成“汇总客诉交负责人确认”。"""
import json

from reviewagent import operations as ops


def point(pid, statement, priority, evidence_id):
    return {"id": pid, "statement": statement, "category": "质量", "severity": 3, "verified": True,
            "frequency": 1, "group_id": "g1", "group_title": "商品A",
            "evidence": [{"review_id": evidence_id, "quote": statement}]}


def analysis(points, improvements):
    return {
        "report": {},
        "enrichment": {
            "pain_points": {"items": points},
            "improvements": {"items": improvements},
            "actions": [],
            "drafts": [],
        },
    }


def test_build_operations_sorts_priority():
    points = [point("p1", "到货有污渍", "P2", "r1"), point("p2", "尺寸偏小", "P0", "r2")]
    improvements = [
        {"pain_point_id": "p1", "action": "更新详情页清洁说明", "priority": "P2", "effort": 1, "impact": 2},
        {"pain_point_id": "p2", "action": "补充尺寸表", "priority": "P0", "effort": 1, "impact": 3},
    ]
    built = ops.build_operations(analysis(points, improvements), "actions")
    assert [item["priority"] for item in built["actions"]] == ["P0", "P2"]


def test_generate_actions_reframes_non_operator_work_and_sorts():
    points = [point("p1", "到货洁净度与手感", "P0", "r1"), point("p2", "尺寸标注不清", "P1", "r2")]
    improvements = [
        {"pain_point_id": "p1", "action": "到货洁净度与手感排查", "priority": "P0", "effort": 2, "impact": 3},
        {"pain_point_id": "p2", "action": "核对尺寸表并更新详情页", "priority": "P1", "effort": 1, "impact": 2},
    ]
    base = analysis(points, improvements)
    base["enrichment"]["pain_points"]["items"] = [dict(item) for item in points]

    class FakeAgent:
        model = "test-model"

        def _call_llm(self, prompt):
            ids = [item["id"] for item in json.loads(prompt.rsplit("\n", 1)[-1])]
            rows = []
            for item_id in ids:
                if item_id.startswith("action-"):
                    rows.append({"id": item_id, "label": "到货洁净度与手感排查",
                                 "detail": "检查来货手感", "metric": "记录"})
            # 第二个 id 给出合规动作
            if len(rows) >= 2:
                rows[1]["label"] = "更新详情页尺寸说明"
            return json.dumps({"items": rows}, ensure_ascii=False)

    result = ops.generate_operations(base, "actions", FakeAgent())
    actions = result["actions"]
    assert [item["priority"] for item in actions] == ["P0", "P1"]
    first = actions[0]
    assert first["execution_scope"] == "需负责人确认"
    assert first["label"].startswith("汇总")
    assert actions[1]["label"] == "更新详情页尺寸说明"


def test_generate_actions_drops_stale_generated_items():
    points = [point("p1", "尺寸标注不清", "P1", "r1")]
    improvements = [{"pain_point_id": "p1", "action": "核对尺寸表", "priority": "P1", "effort": 1, "impact": 2}]
    base = analysis(points, improvements)
    stale = {"id": "action-stale", "priority": "P2", "label": "旧动作", "evidence_ids": ["r1"], "edited": False}

    class FakeAgent:
        model = "test-model"

        def _call_llm(self, prompt):
            ids = [item["id"] for item in json.loads(prompt.rsplit("\n", 1)[-1])]
            return json.dumps({"items": [{"id": ids[0], "label": "核对尺寸表并更新说明",
                                          "detail": "更新页面", "metric": "记录"}]}, ensure_ascii=False)

    base["enrichment"]["actions"] = [stale]
    result = ops.generate_operations(base, "actions", FakeAgent())
    labels = [item["label"] for item in result["actions"]]
    assert "旧动作" not in labels

def test_content_topic_template_is_xhs_post():
    points = [point("p1", "毛绒玩具开线", "P1", "r1")]
    improvements = [{"pain_point_id": "p1", "action": "检查缝线", "priority": "P1", "effort": 1, "impact": 2}]
    base = analysis(points, improvements)
    built = ops.build_operations(base, "content_topic")
    topics = [d for d in built["drafts"] if d["kind"] == "content_topic"]
    assert topics and topics[0]["channel"] == "小红书"
    assert "配图建议" in topics[0]["body"] and "话题" in topics[0]["body"]


def test_content_topic_generation_forces_xhs_channel():
    points = [point("p1", "毛绒玩具开线", "P1", "r1")]
    improvements = [{"pain_point_id": "p1", "action": "检查缝线", "priority": "P1", "effort": 1, "impact": 2}]
    base = analysis(points, improvements)

    class FakeAgent:
        model = "test-model"

        def _call_llm(self, prompt):
            ids = [item["id"] for item in json.loads(prompt.rsplit("\n", 1)[-1])]
            return json.dumps({"items": [{"id": ids[0], "title": "开线了？先别扔，这样处理",
                                          "body": "正文：我家这只用了两周就开线……\n配图建议：封面实拍\n话题：#避坑",
                                          "channel": "公众号"}]}, ensure_ascii=False)

    result = ops.generate_operations(base, "content_topic", FakeAgent())
    generated = [d for d in result["drafts"] if d["kind"] == "content_topic"]
    assert generated and generated[0]["channel"] == "小红书"
    assert "配图建议" in generated[0]["body"]

def test_content_topic_accepts_list_and_structured_body():
    points = [point("p1", "毛绒玩具开线", "P1", "r1")]
    improvements = [{"pain_point_id": "p1", "action": "检查缝线", "priority": "P1", "effort": 1, "impact": 2}]
    base = analysis(points, improvements)

    class FakeAgent:
        model = "test-model"

        def _call_llm(self, prompt):
            ids = [item["id"] for item in json.loads(prompt.rsplit("\n", 1)[-1])]
            return json.dumps([{"id": ids[0], "title": "开线了先别扔",
                                "body": {"正文": "用了两周就开线……", "配图建议": "封面实拍", "话题": "#避坑"}}],
                              ensure_ascii=False)

    result = ops.generate_operations(base, "content_topic", FakeAgent())
    drafts = [d for d in result["drafts"] if d["kind"] == "content_topic" and d.get("generation_method") == "model"]
    assert drafts
    assert drafts[0]["channel"] == "小红书"
    assert "配图建议" in drafts[0]["body"]

def test_selling_point_accepts_list_response():
    points = [point("p1", "毛绒玩具手感好", "P1", "r1")]
    improvements = [{"pain_point_id": "p1", "action": "突出手感卖点", "priority": "P1", "effort": 1, "impact": 2}]
    base = analysis(points, improvements)

    class FakeAgent:
        model = "test-model"

        def _call_llm(self, prompt):
            ids = [item["id"] for item in json.loads(prompt.rsplit("\n", 1)[-1])]
            return json.dumps([{"id": ids[0], "title": "手感卖点", "body": "毛绒细腻", "channel": "商品详情页"}],
                              ensure_ascii=False)

    result = ops.generate_operations(base, "selling_point", FakeAgent())
    generated = [d for d in result["drafts"] if d["kind"] == "selling_point" and d.get("generation_method") == "model"]
    assert generated and generated[0]["title"] == "手感卖点"
    assert "schedule" not in ops.ALLOWED_KINDS
