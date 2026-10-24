"""v5 逐句定时双语字幕（subtitles）单元测试。"""
from app.media import subtitles as st


def test_split_dialogue_to_cues():
    cues = st.split_dialogue_to_cues("你好。你来了！", 6)
    assert len(cues) == 2
    assert cues[0]["zh"] == "你好。"
    assert cues[1]["zh"] == "你来了！"
    assert cues[0]["start"] == 0.0
    assert cues[0]["end"] == cues[1]["start"]      # 无缝衔接
    assert cues[-1]["end"] == 6.0                  # 末句到结尾
    assert cues[0]["en"] == "" and cues[0]["speaker"] == ""


def test_split_empty_and_maxcues():
    assert st.split_dialogue_to_cues("", 5) == []
    cues = st.split_dialogue_to_cues("。".join(["句%d" % i for i in range(20)]), 10, max_cues=8)
    assert len(cues) <= 8


def test_split_strips_markup_and_extracts_speaker():
    text = "苏青鱼（直视老板，语气冷）：「你不用管给谁用。我只要货真价实。」"
    cues = st.split_dialogue_to_cues(text, 6, speakers=["苏青鱼"])
    zhs = [c["zh"] for c in cues]
    assert all(("（" not in z and "「" not in z and "」" not in z) for z in zhs)  # 清掉提示与引号
    assert cues[0]["speaker"] == "苏青鱼"                                          # 抽出说话人
    assert "你不用管给谁用" in zhs[0]
    assert any("货真价实" in z for z in zhs)


def test_short_sentence_kept_whole():
    # 24字 ≤ _SPLIT_CHARS(30)：整句作为一条 cue（烧录时折行），不再按逗号切碎 → 节奏更稳
    cues = st.split_dialogue_to_cues("老板，我要天地银行的冥币，最大面额，有多少要多少。", 8)
    assert len(cues) == 1
    assert cues[0]["zh"].startswith("老板")


def test_very_long_sentence_split_on_commas():
    # 超过 _SPLIT_CHARS 的长句才按逗号再拆
    text = "第一段时间比较长的内容，第二段时间也比较长的内容，第三段内容也比较长一些。"
    cues = st.split_dialogue_to_cues(text, 10)
    assert len(cues) >= 2
    assert all(len(c["zh"]) <= st._SPLIT_CHARS for c in cues)


def test_timing_min_duration_no_flash():
    # 台词很短但镜头很长：每句不低于最短时长比例，且填满镜头、无缝衔接
    cues = st.split_dialogue_to_cues("走吧。好。", 10)
    assert len(cues) == 2
    for c in cues:
        assert c["end"] - c["start"] >= 1.0          # 不会一闪而过
    assert cues[0]["start"] == 0.0 and cues[-1]["end"] == 10.0


def test_cue_text_wraps_long_line():
    cue = {"zh": "这是一句非常非常非常非常非常非常非常长的台词需要折行显示", "en": "", "speaker": ""}
    out = st._cue_text(cue, "zh")
    assert "\n" in out                                 # 折成多行
    assert all(len(ln) <= st._MAX_CHARS for ln in out.split("\n"))


def test_proportional_timing_monotonic():
    cues = st.split_dialogue_to_cues("短句。这是一个比较长一些的句子！", 10)
    assert len(cues) >= 2
    for a, b in zip(cues, cues[1:]):
        assert a["end"] == b["start"]
        assert a["start"] < a["end"]
    assert cues[0]["start"] == 0.0 and cues[-1]["end"] == 10.0



def test_cue_text_bilingual():
    cue = {"zh": "你好", "en": "Hi", "speaker": "甲"}
    # 说话人仅用于对应角色，不打进字幕文本
    assert st._cue_text(cue, "both") == "你好\nHi"
    assert st._cue_text(cue, "zh") == "你好"
    assert st._cue_text(cue, "en") == "Hi"
    assert "甲" not in st._cue_text(cue, "both")


def test_default_subtitles():
    cfg = st.default_subtitles("你好。再见！", 4)
    assert cfg["enabled"] and cfg["position"] == "bottom" and cfg["bilingual"] == "both"
    assert len(cfg["cues"]) == 2


def test_yexpr_positions():
    assert st._yexpr("center") == "(h-th)/2"
    assert st._yexpr("top") == str(st._MARGIN)
    assert st._yexpr("bottom") == "h-th-%d" % st._MARGIN


def test_burn_disabled_or_empty_returns_original(tmp_path):
    vp = tmp_path / "v.mp4"
    vp.write_bytes(b"x")
    assert st.burn_subtitles_timed(vp, {"enabled": False, "cues": [{"zh": "x"}]}) == str(vp)
    assert st.burn_subtitles_timed(vp, {"enabled": True, "cues": []}) == str(vp)


def test_burn_timed_builds_chained_filters(monkeypatch, tmp_path):
    vp = tmp_path / "v.mp4"
    vp.write_bytes(b"x")
    seen = {}
    monkeypatch.setattr(st, "probe_duration", lambda p: 4.0)
    monkeypatch.setattr(st, "find_cjk_font", lambda: "C:/Windows/Fonts/msyh.ttc")

    class _P:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **k):
        seen["cmd"] = list(cmd)
        seen["cwd"] = k.get("cwd")
        (tmp_path / cmd[-1]).write_bytes(b"out")   # cmd[-1]=输出裸名
        return _P()

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    cfg = {"enabled": True, "position": "bottom", "bilingual": "both", "font_size": 30,
           "cues": [{"start": 0, "end": 2, "zh": "甲", "en": "A"},
                    {"start": 2, "end": 4, "zh": "乙", "en": "B"}]}
    out = st.burn_subtitles_timed(vp, cfg, out_path=tmp_path / "o.mp4")
    assert out == str(tmp_path / "o.mp4")
    vf = seen["cmd"][seen["cmd"].index("-vf") + 1]
    assert vf.count("drawtext") == 2                       # 两句 = 两个 drawtext 链式
    assert "enable='between(t,0.00,2.00)'" in vf            # 逐句定时窗口
    assert "enable='between(t,2.00,4.00)'" in vf
    assert "fontfile='C\\:/Windows/Fonts/msyh.ttc'" in vf   # 字体转义
    assert seen["cwd"] == str(tmp_path)
    assert not list(tmp_path.glob("*_cue*.txt"))            # 临时文本已清理


def test_reading_time_and_suggest_split():
    cues = [{"zh": "一二三四五六七八九十"} for _ in range(6)]   # 6句各10字
    assert st.reading_time(cues) == 12.0                        # 6 * max(1.1, 10/5=2)
    assert st.suggest_split_count(cues, 5) == 3                 # ceil(12/5)=3
    assert st.suggest_split_count(cues, 20) == 1                # 12 <= 20*1.25 → 不拆


def test_suggest_split_short_dialogue():
    cues = [{"zh": "走吧。"}, {"zh": "好。"}]
    assert st.suggest_split_count(cues, 10) == 1                # 阅读时长短，无需拆
    assert st.suggest_split_count([{"zh": "单句"}], 3) == 1      # 不足两句


def test_distribute_cues_keeps_order_and_all():
    cues = [{"zh": "a" * 10}, {"zh": "b" * 10}, {"zh": "c" * 10}, {"zh": "d" * 10}]
    groups = st.distribute_cues(cues, 2)
    assert len(groups) == 2
    flat = [c for g in groups for c in g]
    assert flat == cues                                         # 不丢句、保顺序
    assert all(len(g) >= 1 for g in groups)                     # 无空组


def test_distribute_cues_parts_ge_len():
    cues = [{"zh": "x"}, {"zh": "y"}]
    groups = st.distribute_cues(cues, 5)                        # parts > 句数
    assert sum(len(g) for g in groups) == 2
    assert all(g for g in groups)

