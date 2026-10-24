import json
from app.pipeline.stage2_cross_chapter_synthesis import _parse_global

SAMPLE_GLOBAL = json.dumps({
    "characters": [
        {"name": "令狐冲", "aliases": ["冲哥"], "role": "protagonist", "description": "华山派大弟子", "traits": ["洒脱"], "first_appearance_chapter": 1},
        {"name": "岳不群", "aliases": [], "role": "antagonist", "description": "华山派掌门", "traits": ["深沉"], "first_appearance_chapter": 2}
    ],
    "relationships": [
        {"from": "令狐冲", "to": "岳不群", "type": "师徒", "description": "情同父子却有裂痕"}
    ],
    "locations": [
        {"name": "华山之巅", "description": "华山最高处", "chapters": [1]}
    ],
    "main_plot": "令狐冲在江湖历练中成长",
    "subplots": ["与岳不群的师徒关系破裂"]
})

def test_parse_global_characters():
    result = _parse_global(SAMPLE_GLOBAL)
    assert len(result.characters) == 2
    assert result.characters[0]["name"] == "令狐冲"

def test_parse_global_relationships():
    result = _parse_global(SAMPLE_GLOBAL)
    assert len(result.relationships) == 1
    assert result.relationships[0]["type"] == "师徒"

def test_parse_global_main_plot():
    result = _parse_global(SAMPLE_GLOBAL)
    assert "令狐冲" in result.main_plot

def test_parse_global_subplots():
    result = _parse_global(SAMPLE_GLOBAL)
    assert len(result.subplots) == 1

def test_parse_global_invalid():
    result = _parse_global("not json")
    assert result.characters == []
