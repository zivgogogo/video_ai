import json
from app.pipeline.stage0_preprocess import Chapter
from app.pipeline.stage1_chapter_analysis import _parse_response

SAMPLE_JSON = json.dumps({
    "new_characters": [
        {"name": "令狐冲", "aliases": ["冲哥"], "description": "华山派大弟子", "traits": ["洒脱"], "role_hint": "protagonist"}
    ],
    "locations": [
        {"name": "华山之巅", "description": "华山最高处", "time_hint": "清晨"}
    ],
    "plot_events": [
        {"summary": "令狐冲站在山巅", "importance": "minor", "characters_involved": ["令狐冲"]}
    ],
    "dialogue_excerpts": []
})

def test_parse_response_json():
    result = _parse_response(0, "第一章", SAMPLE_JSON)
    assert len(result.new_characters) == 1
    assert result.new_characters[0]["name"] == "令狐冲"
    assert len(result.locations) == 1
    assert len(result.plot_events) == 1

def test_parse_response_with_code_fence():
    fenced = f"```json\n{SAMPLE_JSON}\n```"
    result = _parse_response(0, "第一章", fenced)
    assert result.new_characters[0]["name"] == "令狐冲"

def test_parse_response_invalid_json():
    result = _parse_response(0, "第一章", "这不是合法的 JSON")
    assert result.raw_response == "这不是合法的 JSON"
    assert result.new_characters == []

def test_analyze_chapter_fields():
    analysis = _parse_response(0, "第一章 华山", SAMPLE_JSON)
    assert analysis.chapter_index == 0
    assert analysis.chapter_title == "第一章 华山"
    assert len(analysis.dialogue_excerpts) == 0
