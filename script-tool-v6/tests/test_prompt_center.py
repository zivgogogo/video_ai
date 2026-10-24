"""v5 Prompt 中心：分镜结构化合并 / 定位 等纯逻辑单元测试。"""
import json

from app.routes import media as md
from app.media import prompt_elements as pe


def test_merge_elements_fills_and_assembles():
    shot = {"shot_number": 1, "scene_title": "场A",
            "video_prompt": "旧段落", "characters_present": ["甲"]}
    md._merge_elements(shot, {"shot_size": "特写", "subject": "甲（黑衣）",
                              "dialogue": "走！", "lighting": ["柔光"]})
    els = shot["elements"]
    assert els["shot_size"] == "特写"
    assert els["lighting"] == ["柔光"]
    assert els["visual_style"] == "电影感写实"        # 兜底风格
    assert els["quality"] == ["电影级", "高清"]        # 兜底画质
    assert "特写" in shot["video_prompt"]
    assert "说：「走！」" in shot["video_prompt"]
    assert shot["dialogue"] == "走！"                 # 顶层兼容字段同步
    assert shot["shot_size"] == "特写"
    assert shot["characters_present"] == ["甲"]       # 未被破坏


def test_merge_elements_preserves_existing():
    shot = {"elements": pe.new_elements()}
    shot["elements"]["color_tone"] = "暖色调"
    md._merge_elements(shot, {"mood": "温馨"})
    assert shot["elements"]["color_tone"] == "暖色调"  # 旧值保留
    assert shot["elements"]["mood"] == "温馨"          # 新值并入


def test_merge_elements_ignores_unknown_and_empty():
    shot = {}
    md._merge_elements(shot, {"unknown_key": "x", "shot_size": "", "mood": "紧张"})
    assert "unknown_key" not in shot["elements"]       # 非法键丢弃
    assert shot["elements"]["shot_size"] == ""         # 空值不覆盖
    assert shot["elements"]["mood"] == "紧张"


def test_merge_elements_idempotent_summary():
    shot = {}
    md._merge_elements(shot, {"subject": "人物", "shot_size": "中景"})
    first = shot["video_prompt"]
    md._merge_elements(shot, {})                        # 再次合并空要素
    assert shot["video_prompt"] == first                # 汇总稳定


def test_find_shot():
    shots = [{"shot_number": 1}, {"shot_number": 2}]
    assert md._find_shot(shots, 2)["shot_number"] == 2
    assert md._find_shot(shots, 9) is None


def test_norm_title_strips_separators():
    assert md._norm_title("诡异降临·公寓") == "诡异降临公寓"
    assert md._norm_title("[内景：白事店，夜]") == "内景白事店夜"


def test_resolve_shot_scenes_exact_contain_lcs():
    scenes = [
        {"index": 0, "title": "[内景：永寿堂白事店，夜]",
         "scene_heading": "[内景：永寿堂白事店，夜]", "location": "永寿堂白事店"},
        {"index": 1, "title": "[内景：苏青鱼租住的公寓，傍晚]",
         "scene_heading": "[内景：苏青鱼租住的公寓，傍晚]", "location": "苏青鱼租住的公寓"},
        {"index": 5, "title": "[内景：苏青鱼租住的公寓，诡异降临前]",
         "scene_heading": "[内景：苏青鱼租住的公寓，诡异降临前]", "location": "苏青鱼租住的公寓"},
    ]
    shots = [
        {"shot_number": 1, "scene_title": "永寿堂白事店"},   # 精确匹配 location
        {"shot_number": 2, "scene_title": "苏青鱼公寓"},       # LCS → scene1
        {"shot_number": 3, "scene_title": "诡异降临·公寓"},     # LCS(含·) → scene5
    ]
    assert md._resolve_shot_scenes(shots, scenes) is True
    assert shots[0]["scene_index"] == 0
    assert shots[1]["scene_index"] == 1
    assert shots[2]["scene_index"] == 5


def test_resolve_shot_scenes_keeps_existing_index():
    scenes = [{"index": 0, "title": "A", "scene_heading": "A", "location": "A"},
              {"index": 1, "title": "B", "scene_heading": "B", "location": "B"}]
    shots = [{"shot_number": 1, "scene_title": "A", "scene_index": 1}]  # 已有且合法
    md._resolve_shot_scenes(shots, scenes)
    assert shots[0]["scene_index"] == 1   # 不被标题匹配覆盖


# ── 视频重新生成：已完成镜头默认跳过并反馈，force 才重做（回归保护）──
def test_post_videos_skip_done_and_force(monkeypatch):
    import asyncio
    shots = [{"shot_number": 1, "video_prompt": "p",
              "characters_present": ["甲"], "duration_seconds": 5}]
    videos = [{"shot_number": 1, "status": "DONE",
               "video_file": "shot_1.mp4", "task_id": "old"}]
    chars = [{"name": "甲", "image_file": "", "image_url": "http://x/jia.png"}]
    monkeypatch.setattr(md.media_store, "load_storyboard", lambda pid: [dict(s) for s in shots])
    monkeypatch.setattr(md.media_store, "load_videos", lambda pid: [dict(v) for v in videos])
    monkeypatch.setattr(md.media_store, "save_videos", lambda pid, v: None)
    monkeypatch.setattr(md.media_store, "load_characters", lambda pid: list(chars))
    calls = {"n": 0}

    async def fake_submit(model, prompt, **k):
        calls["n"] += 1
        return {"task_id": "new", "model": model}

    monkeypatch.setattr(md.ds, "submit_video_unified", fake_submit)

    # 不带 force：已完成镜头被跳过，且有 skipped 反馈，不调用提交
    r = asyncio.run(md.post_videos("pid", {"model": "happyhorse-1.1-r2v"}))
    assert r["skipped"] == [1]
    assert r["submitted"] == []
    assert calls["n"] == 0

    # 带 force：强制重做，提交成功
    r2 = asyncio.run(md.post_videos("pid", {"model": "happyhorse-1.1-r2v", "force": True}))
    assert r2["submitted"] == [1]
    assert r2["skipped"] == []
    assert calls["n"] == 1


# ── 角色/场景一致性：参考图↔名字绑定 ──────────────────────────
def _png(tmp_path, name):
    (tmp_path / name).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)


def test_img_token():
    assert md._img_token("happyhorse-1.1-r2v", 1) == "[Image 1]"
    assert md._img_token("wan3.0-video", 2) == "图2"


def test_char_refs_named_skips_imageless(monkeypatch, tmp_path):
    monkeypatch.setattr(md.media_store, "image_path", lambda pid, f: tmp_path / f)
    _png(tmp_path, "jia.png")
    char_map = {
        "甲": {"name": "甲", "image_file": "jia.png", "image_url": ""},
        "乙": {"name": "乙", "image_file": "", "image_url": "http://x/yi.png"},
        "丙": {"name": "丙", "image_file": "", "image_url": ""},
    }
    shot = {"characters_present": ["甲", "乙", "丙", "丁"]}
    named, imageless = md._char_refs_named("pid", shot, char_map)
    assert [n for n, _ in named] == ["甲", "乙"]              # 保序、跳过无图
    assert named[0][1].startswith("data:image/png;base64,")   # 本地图转 base64
    assert named[1][1] == "http://x/yi.png"                    # 回退公网 url
    assert set(imageless) == {"丙", "丁"}


def test_build_reference_media_char_first_scene_last(monkeypatch, tmp_path):
    monkeypatch.setattr(md.media_store, "image_path", lambda pid, f: tmp_path / f)
    monkeypatch.setattr(md.media_store, "load_scene_refs",
                        lambda pid: {"3": {"file": "sceneref_3.png"}})
    _png(tmp_path, "sceneref_3.png")
    _png(tmp_path, "jia.png")
    char_map = {"甲": {"name": "甲", "image_file": "jia.png", "image_url": ""}}
    shot = {"characters_present": ["甲"], "scene_index": 3}
    urls, prefix = md._build_reference_media("pid", shot, char_map, "happyhorse-1.1-r2v")
    assert len(urls) == 2                       # 甲 + 场景图
    assert "[Image 1]=甲" in prefix              # 角色优先占主参考位（修复一致性下降）
    assert "[Image 2]=场景/环境" in prefix        # 场景图排最后
    assert "严格保持" in prefix and "场景空间" in prefix


def test_build_reference_media_scene_off(monkeypatch, tmp_path):
    # use_scene=False → 不注入场景图，人物参考占满权重
    monkeypatch.setattr(md.media_store, "image_path", lambda pid, f: tmp_path / f)
    monkeypatch.setattr(md.media_store, "load_scene_refs",
                        lambda pid: {"3": {"file": "sceneref_3.png"}})
    _png(tmp_path, "sceneref_3.png")
    _png(tmp_path, "jia.png")
    char_map = {"甲": {"name": "甲", "image_file": "jia.png"}}
    shot = {"characters_present": ["甲"], "scene_index": 3}
    urls, prefix = md._build_reference_media(
        "pid", shot, char_map, "happyhorse-1.1-r2v", use_scene=False)
    assert len(urls) == 1                        # 只有甲，无场景图
    assert "[Image 1]=甲" in prefix
    assert "场景" not in prefix



def test_build_reference_media_no_scene(monkeypatch, tmp_path):
    monkeypatch.setattr(md.media_store, "image_path", lambda pid, f: tmp_path / f)
    monkeypatch.setattr(md.media_store, "load_scene_refs", lambda pid: {})
    _png(tmp_path, "jia.png")
    char_map = {"甲": {"name": "甲", "image_file": "jia.png"}}
    urls, prefix = md._build_reference_media(
        "pid", {"characters_present": ["甲"], "scene_index": 0}, char_map, "wan3.0-video")
    assert len(urls) == 1
    assert "图1=甲" in prefix                    # wan3.0 用「图n」


def test_scene_refs_roundtrip(monkeypatch, tmp_path):
    from app.media import media_store as ms
    monkeypatch.setattr(ms, "MEDIA_DIR", tmp_path)
    assert ms.load_scene_refs("p1") == {}
    ms.save_scene_refs("p1", {"0": {"file": "s0.png", "url": "/x"}})
    assert ms.load_scene_refs("p1") == {"0": {"file": "s0.png", "url": "/x"}}


def test_post_videos_captures_subtitles_from_dialogue(monkeypatch):
    import asyncio
    shots = [{"shot_number": 1, "video_prompt": "p", "dialogue": "你好。再见！",
              "characters_present": ["甲"], "duration_seconds": 4}]
    chars = [{"name": "甲", "image_file": "", "image_url": "http://x/j.png"}]
    monkeypatch.setattr(md.media_store, "load_storyboard", lambda pid: [dict(s) for s in shots])
    monkeypatch.setattr(md.media_store, "load_videos", lambda pid: [])
    saved = {}
    monkeypatch.setattr(md.media_store, "save_videos", lambda pid, v: saved.__setitem__("v", v))
    monkeypatch.setattr(md.media_store, "load_characters", lambda pid: list(chars))

    async def fake_submit(model, prompt, **k):
        return {"task_id": "t", "model": model}

    monkeypatch.setattr(md.ds, "submit_video_unified", fake_submit)
    asyncio.run(md.post_videos("pid", {"model": "happyhorse-1.1-r2v", "subtitle": True}))
    entry = saved["v"][0]
    assert entry["subtitles"]["enabled"] is True
    assert len(entry["subtitles"]["cues"]) == 2            # 由台词自动分句
    assert entry["subtitles"]["cues"][0]["zh"] == "你好。"


def test_split_shot_endpoint(monkeypatch):
    import asyncio
    shot = {"shot_number": 1, "scene_index": 0, "scene_title": "场A",
            "duration_seconds": 5, "characters_present": ["甲"],
            "elements": {"dialogue": "第一句话。第二句话。第三句话。第四句话。",
                         "subject": "甲", "visual_style": "电影感写实"},
            "dialogue": "第一句话。第二句话。第三句话。第四句话。"}
    monkeypatch.setattr(md.media_store, "load_storyboard", lambda pid: [dict(shot)])
    monkeypatch.setattr(md.media_store, "load_characters", lambda pid: [{"name": "甲"}])
    saved = {}
    monkeypatch.setattr(md.media_store, "save_storyboard",
                        lambda pid, s: saved.__setitem__("s", s))
    r = asyncio.run(md.split_shot("pid", 1, {"parts": 2}))
    assert r["ok"] and r["added"] == 2 and r["total"] == 2
    new = saved["s"]
    assert [s["shot_number"] for s in new] == [1, 2]        # 全局重编号
    assert new[0]["dialogue"] != new[1]["dialogue"]         # 对白被分配到两段
    assert new[0]["subtitles"]["cues"] and new[1]["subtitles"]["cues"]
    assert new[0]["scene_title"] == "场A"                   # 继承场景
    assert new[0].get("video_prompt")                       # 重算汇总
    assert "confirmed" not in new[0]                        # 拆分后需重新确认


def test_refine_split_parts(monkeypatch):
    import asyncio
    from app.media import storyboard as sb
    payload = json.dumps({"parts": [
        {"elements": {"action": "甲递出冥币", "shot_size": "近景", "dialogue": "第一句话。"}},
        {"elements": {"action": "乙皱眉清点", "shot_size": "特写", "dialogue": "第二句话。"}},
    ]}, ensure_ascii=False)

    async def fake_gen(provider, messages, **kw):
        fake_gen.prompt = messages[0]["content"]
        return payload

    monkeypatch.setattr(sb, "generate_with_pool_fallback", fake_gen)
    monkeypatch.setattr(sb, "create_ai_provider", lambda p=None: object())
    base = {"subject": "甲乙", "scene": "店内", "environment": "昏暗",
            "visual_style": "电影感写实", "action": "原动作"}
    out = asyncio.run(sb.refine_split_parts("场A", base, ["甲", "乙"],
                                            ["第一句话。", "第二句话。"]))
    assert len(out) == 2
    assert out[0]["action"] == "甲递出冥币" and out[0]["shot_size"] == "近景"
    assert out[0]["scene"] == "店内"                 # 继承一致字段
    assert out[0]["dialogue"] == "第一句话。"          # 台词以分配为准
    assert out[1]["action"] == "乙皱眉清点"
    assert "段1台词：第一句话。" in fake_gen.prompt    # 提示词带各段台词


def test_refine_split_parts_failure_returns_none(monkeypatch):
    import asyncio
    from app.media import storyboard as sb

    async def boom(provider, messages, **kw):
        raise RuntimeError("down")

    monkeypatch.setattr(sb, "generate_with_pool_fallback", boom)
    monkeypatch.setattr(sb, "create_ai_provider", lambda p=None: object())
    out = asyncio.run(sb.refine_split_parts("场A", {}, [], ["a。", "b。"]))
    assert out == [None, None]                        # 失败降级：沿用原要素


def test_split_shot_ai_uses_refined(monkeypatch):
    import asyncio
    shot = {"shot_number": 1, "scene_index": 0, "scene_title": "场A", "duration_seconds": 5,
            "characters_present": ["甲"],
            "elements": {"dialogue": "第一句话。第二句话。第三句话。第四句话。",
                         "action": "原动作", "scene": "店内"},
            "dialogue": "第一句话。第二句话。第三句话。第四句话。"}
    monkeypatch.setattr(md.media_store, "load_storyboard", lambda pid: [dict(shot)])
    monkeypatch.setattr(md.media_store, "load_characters", lambda pid: [{"name": "甲"}])
    saved = {}
    monkeypatch.setattr(md.media_store, "save_storyboard",
                        lambda pid, s: saved.__setitem__("s", s))

    async def fake_refine(scene_title, base_el, chars, parts_dialogue):
        return [dict(base_el, action="AI动作%d" % i, dialogue=d)
                for i, d in enumerate(parts_dialogue)]

    monkeypatch.setattr(md.sb, "refine_split_parts", fake_refine)
    r = asyncio.run(md.split_shot("pid", 1, {"parts": 2, "ai": True}))
    assert r["added"] == 2
    new = saved["s"]
    assert new[0]["elements"]["action"] == "AI动作0"   # 用了 AI 重配画面
    assert new[1]["elements"]["action"] == "AI动作1"
    assert new[0]["elements"]["scene"] == "店内"       # 继承一致字段
