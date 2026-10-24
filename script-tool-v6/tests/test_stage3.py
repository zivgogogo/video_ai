import json
from app.pipeline.stage3_script_structure import _parse_structure

SAMPLE_STRUCTURE = json.dumps({
    "scenes": [
        {"act": 1, "episode": 1, "sequence": 1, "location": "华山之巅", "time": "清晨", "setting_description": "云雾缭绕", "characters_present": ["令狐冲"], "summary": "令狐冲出场", "source_chapter": 1},
        {"act": 1, "episode": 1, "sequence": 2, "location": "正气堂", "time": "日间", "setting_description": "庄严肃穆", "characters_present": ["令狐冲", "岳不群"], "summary": "师徒对峙", "source_chapter": 2}
    ],
    "episode_summaries": [
        {"episode": 1, "title": "剑气之争", "summary": "令狐冲回山", "scene_indices": [0, 1], "cliffhanger": "风清扬现身"}
    ],
    "beat_sheet": [
        {"beat": "开场画面", "scene_index": 0, "description": "华山之巅的孤寂"}
    ]
})

def test_parse_structure_scenes():
    result = _parse_structure(SAMPLE_STRUCTURE, "tv_series")
    assert len(result.scenes) == 2
    assert result.scenes[0].id == "scene_001"
    assert result.scenes[1].id == "scene_002"

def test_parse_structure_scene_fields():
    result = _parse_structure(SAMPLE_STRUCTURE, "film")
    s0 = result.scenes[0]
    assert s0.location == "华山之巅"
    assert s0.time == "清晨"
    assert s0.characters_present == ["令狐冲"]
    assert s0.summary != ""

def test_parse_structure_episode_summaries():
    result = _parse_structure(SAMPLE_STRUCTURE, "tv_series")
    assert len(result.episode_summaries) == 1
    assert result.episode_summaries[0]["title"] == "剑气之争"

def test_parse_structure_beat_sheet():
    result = _parse_structure(SAMPLE_STRUCTURE, "film")
    assert len(result.beat_sheet) == 1

def test_parse_structure_invalid():
    result = _parse_structure("bad", "film")
    assert result.scenes == []
