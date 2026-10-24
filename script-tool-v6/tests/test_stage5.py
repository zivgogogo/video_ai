from app.pipeline.stage2_cross_chapter_synthesis import GlobalAnalysis
from app.pipeline.stage3_script_structure import ScriptStructure
from app.pipeline.stage4_scene_generation import GeneratedScene
from app.pipeline.stage5_assembly import assemble

def make_fixtures():
    meta = {"title": "剑出华山", "source_novel": "笑傲江湖", "source_author": "金庸", "script_type": "tv_series", "version": "0.1.0", "created_at": "2026-06-05", "language": "zh-CN"}
    config = {"target_episodes": 40, "style": "武侠"}
    ga = GlobalAnalysis(
        characters=[
            {"name": "令狐冲", "role": "protagonist", "description": "华山派大弟子", "traits": ["洒脱"]},
            {"name": "岳不群", "role": "antagonist", "description": "华山派掌门", "traits": ["深沉"]},
        ],
        relationships=[{"from": "令狐冲", "to": "岳不群", "type": "师徒", "description": "情同父子"}]
    )
    structure = ScriptStructure(script_type="tv_series", episode_summaries=[
        {"episode": 1, "title": "剑气之争", "summary": "令狐冲回山"}
    ])
    gs1 = GeneratedScene(id="scene_001", act=1, episode=1, sequence=1, location="正气堂", time="清晨", characters_present=["令狐冲", "岳不群"],
        content=[
            {"type": "action", "text": "令狐冲步入正气堂。"},
            {"type": "dialogue", "character": "岳不群", "text": "冲儿，你又去饮酒了？", "direction": "失望"},
        ])
    return meta, config, ga, structure, [gs1]

def test_assemble_produces_valid_yaml():
    result = assemble(*make_fixtures())
    assert result.is_valid
    assert "剑出华山" in result.yaml_text
    assert "scene_001" in result.yaml_text

def test_assemble_includes_characters():
    result = assemble(*make_fixtures())
    assert "char_001" in result.yaml_text or "令狐冲" in result.yaml_text

def test_assemble_includes_extensions():
    result = assemble(*make_fixtures())
    assert "tv_series" in result.yaml_text or "episode_summaries" in result.yaml_text

def test_assemble_validation_no_title():
    meta, config, ga, structure, scenes = make_fixtures()
    meta["title"] = ""
    result = assemble(meta, config, ga, structure, scenes)
    assert not result.is_valid

def test_assemble_validation_no_scenes():
    meta, config, ga, structure, _ = make_fixtures()
    result = assemble(meta, config, ga, structure, [])
    assert not result.is_valid
