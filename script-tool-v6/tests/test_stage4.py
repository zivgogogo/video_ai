import json
from app.pipeline.stage3_script_structure import ScenePlan
from app.pipeline.stage4_scene_generation import _parse_scene

SAMPLE_SCENE_JSON = json.dumps({
    "content": [
        {"type": "action", "text": "令狐冲步入正气堂，衣衫不整。"},
        {"type": "dialogue", "character": "岳不群", "text": "冲儿，你昨夜又去后山饮酒了？", "direction": "语重心长"},
        {"type": "action", "text": "令狐冲低头不语。"},
        {"type": "transition", "text": "CUT TO:"}
    ]
})

def test_parse_scene_content():
    plan = ScenePlan(id="scene_001", location="正气堂", time="清晨", characters_present=["令狐冲", "岳不群"])
    result = _parse_scene(plan, SAMPLE_SCENE_JSON)
    assert len(result.content) == 4
    assert result.content[0]["type"] == "action"
    assert result.content[1]["type"] == "dialogue"
    assert result.content[1]["character"] == "岳不群"
    assert result.content[3]["type"] == "transition"

def test_parse_scene_invalid():
    plan = ScenePlan(id="scene_001", location="", time="")
    result = _parse_scene(plan, "bad json")
    assert result.content == []
