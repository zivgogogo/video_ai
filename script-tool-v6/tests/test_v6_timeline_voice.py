"""v6 新增：画面时间轴（时间戳定向编辑）+ 角色配音（CosyVoice）纯逻辑单测。

只依赖 app.media.prompt_elements（无三方依赖）与 app.media.voice_media（依赖 config），
不触碰 fastapi / 数据库，便于快速回归。
"""
import app.media.prompt_elements as pe
import app.media.voice_media as vm


# ── 画面时间轴 beats（时间戳定向编辑）──────────────────────
def test_normalize_beats_sorts_and_swaps():
    beats = pe.normalize_beats([
        {"start": 5, "end": 2, "action": "转身"},      # end<start 应交换
        {"start": 0, "end": 3, "action": "入场"},
    ], duration=10)
    assert beats[0]["start"] == 0 and beats[0]["end"] == 3     # 按 start 排序
    assert beats[1]["start"] == 2 and beats[1]["end"] == 5     # 交换后


def test_normalize_beats_drops_empty_and_clamps():
    beats = pe.normalize_beats([
        {"action": "", "camera": "", "dialogue": ""},   # 全空 → 丢弃
        {"start": 0, "end": 99, "action": "奔跑"},      # end 超时长 → 夹到 duration
    ], duration=10)
    assert len(beats) == 1
    assert beats[0]["end"] == 10


def test_assemble_timeline_body_format():
    body = pe.assemble_timeline_body([
        {"start": 0, "end": 5, "action": "走进教室", "camera": "跟拍"},
        {"start": 5, "end": 10, "action": "坐下", "dialogue": "终于到了"},
    ])
    assert body == "0-5秒：走进教室（跟拍）；5-10秒：坐下，说：「终于到了」"


def test_assemble_timeline_body_empty():
    assert pe.assemble_timeline_body([]) == ""
    assert pe.assemble_timeline_body(None) == ""


def test_assemble_video_prompt_uses_beats_when_present():
    el = {"subject": "小明", "scene": "教室", "shot_size": "中景"}
    p_with = pe.assemble_video_prompt(el, [{"start": 0, "end": 5, "action": "走进教室"}])
    p_without = pe.assemble_video_prompt(el)
    assert "0-5秒：走进教室" in p_with
    assert "0-5秒" not in p_without            # 无 beats → 走整段小作文
    assert "小明" in p_without


# ── 角色配音 CosyVoice ──────────────────────────────────
def test_normalize_emotion_maps_cn_and_en():
    assert vm.normalize_emotion("愤怒") == "angry"
    assert vm.normalize_emotion("happy") == "happy"
    assert vm.normalize_emotion(" unknown ") == ""
    assert vm.normalize_emotion("") == ""


def test_build_instruction_format():
    assert vm.build_instruction("happy") == "你说话的情感是happy。"
    assert vm.build_instruction("悲伤") == "你说话的情感是sad。"
    assert "角色" in vm.build_instruction("happy", role="一个旁白")
    assert vm.build_instruction("") == ""            # 无情感 → 空指令


def test_voice_supports_instruct():
    assert vm.voice_supports_instruct("longanyang") is True
    assert vm.voice_supports_instruct("longxiaochun_v3") is False
    assert vm.voice_supports_instruct("不存在的音色") is False


def test_normalize_voice_config_clamps_and_degrades():
    cfg = vm.normalize_voice_config({
        "voice": "longanyang", "emotion": "愤怒",
        "speech_rate": 5, "pitch_rate": 0.1, "volume": 999})
    assert cfg["voice"] == "longanyang"
    assert cfg["emotion"] == "angry"
    assert cfg["speech_rate"] == 2.0        # 上限 2.0
    assert cfg["pitch_rate"] == 0.5         # 下限 0.5
    assert cfg["volume"] == 100             # 上限 100
    # 不支持情感指令的音色 → 情感自动降级为空
    cfg2 = vm.normalize_voice_config({"voice": "longxiaochun_v3", "emotion": "愤怒"})
    assert cfg2["emotion"] == ""


def test_normalize_voice_config_default_voice():
    cfg = vm.normalize_voice_config({})
    assert cfg["voice"]                     # 落到默认音色
    assert 0.5 <= cfg["speech_rate"] <= 2.0
    assert 0 <= cfg["volume"] <= 100


def test_voice_options_shape():
    opt = vm.voice_options()
    assert opt["library"] and opt["emotions"] and opt["ranges"] and opt["defaults"]
    assert len(vm.VOICES_BY_ID) >= 40
    for v in vm.VOICES_BY_ID.values():      # 每个音色字段齐备
        assert v["id"] and v["name"] and "instruct" in v
    # 情感选项与 CosyVoice 固定 7 值一致
    assert {e["value"] for e in opt["emotions"]} == set(vm.EMOTIONS.keys())
