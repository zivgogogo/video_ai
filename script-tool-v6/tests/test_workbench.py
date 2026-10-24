"""v4 创作工作台 / 新视频模型 单元测试（不触网、不依赖真实 ffmpeg 执行）。

覆盖：
- submit_video_unified 各模式 payload 正确性（media type、happyhorse-i2v 不发 ratio/audio、
  wan3.0 发 audio、watermark 恒为 false）；
- _clamp_duration 时长夹取；media 构造器；file_to_data_uri 上限；
- extract_last_frame 命令拼装与失败处理（mock subprocess）；
- workbench_store 读写；_resolve_image_input；gen_video 各模式分支与校验。
"""
import asyncio

import pytest

from app.media import dashscope_media as ds
from app.media import workbench_store as wstore
from app.routes import workbench as wb


# ── 假的 httpx.AsyncClient：捕获请求 payload，返回固定 task_id ──
class _FakeResp:
    status_code = 200
    text = ""

    def json(self):
        return {"output": {"task_id": "tid-123"}}


class _FakeClient:
    captured = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeClient.captured.clear()
        _FakeClient.captured.update({"url": url, "headers": headers, "json": json})
        return _FakeResp()


@pytest.fixture
def fake_http(monkeypatch):
    monkeypatch.setattr(ds.httpx, "AsyncClient", _FakeClient)
    _FakeClient.captured.clear()
    return _FakeClient.captured


# ── media 构造器 ──────────────────────────────────────────
def test_media_builders():
    assert ds.first_frame_media("u") == [{"type": "first_frame", "url": "u"}]
    assert ds.first_last_media("a", "b") == [
        {"type": "first_frame", "url": "a"}, {"type": "last_frame", "url": "b"}]
    assert ds.first_last_media("a", "") == [{"type": "first_frame", "url": "a"}]
    assert ds.ref_media(["a", "b"]) == [
        {"type": "reference_image", "url": "a"},
        {"type": "reference_image", "url": "b"}]
    assert ds.ref_media([]) == []


def test_clamp_duration():
    assert ds._clamp_duration("happyhorse-1.1-i2v", 1) == 3
    assert ds._clamp_duration("happyhorse-1.1-i2v", 99) == 15
    assert ds._clamp_duration("happyhorse-1.1-r2v", 5) == 5
    assert ds._clamp_duration("wan3.0-video", 1) == 2
    assert ds._clamp_duration("wan3.0-video", 99) == 30
    assert ds._clamp_duration("wan3.0-video", -1) == -1


# ── submit_video_unified：各模型 payload ──────────────────
def test_submit_i2v_no_ratio_no_audio(fake_http):
    res = asyncio.run(ds.submit_video_unified(
        "happyhorse-1.1-i2v", "a cat", media=ds.first_frame_media("http://x/1.png"),
        resolution="720P", ratio="16:9", duration=5))
    assert res == {"task_id": "tid-123", "model": "happyhorse-1.1-i2v"}
    p = fake_http["json"]
    assert p["model"] == "happyhorse-1.1-i2v"
    assert p["input"]["media"] == [{"type": "first_frame", "url": "http://x/1.png"}]
    assert p["parameters"]["watermark"] is False
    assert "ratio" not in p["parameters"]     # i2v 比例随首帧
    assert "audio" not in p["parameters"]     # 非 wan3 不发 audio
    assert fake_http["headers"]["X-DashScope-Async"] == "enable"


def test_submit_r2v_keeps_ratio(fake_http):
    asyncio.run(ds.submit_video_unified(
        "happyhorse-1.1-r2v", "scene", media=ds.ref_media(["a", "b"]),
        ratio="16:9", duration=20))
    p = fake_http["json"]
    assert p["model"] == "happyhorse-1.1-r2v"
    assert len(p["input"]["media"]) == 2
    assert p["parameters"]["ratio"] == "16:9"
    assert p["parameters"]["duration"] == 15   # happyhorse 夹到 3-15
    assert "audio" not in p["parameters"]


def test_submit_wan3_t2v_has_audio(fake_http):
    asyncio.run(ds.submit_video_unified(
        "wan3.0-video", "a cat runs", media=None, ratio="16:9", duration=8,
        audio=False, prompt_extend=True))
    p = fake_http["json"]
    assert p["model"] == "wan3.0-video"
    assert "media" not in p["input"]           # 纯文生视频
    assert p["parameters"]["audio"] is False
    assert p["parameters"]["ratio"] == "16:9"
    assert p["parameters"]["prompt_extend"] is True
    assert p["parameters"]["duration"] == 8


def test_submit_requires_prompt_or_media(fake_http):
    with pytest.raises(RuntimeError):
        asyncio.run(ds.submit_video_unified("wan3.0-video", "", media=None))


# ── file_to_data_uri 上限 ────────────────────────────────
def test_file_to_data_uri_limit(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    assert ds.file_to_data_uri(p, max_bytes=1000).startswith("data:image/png;base64,")
    with pytest.raises(RuntimeError):
        ds.file_to_data_uri(p, max_bytes=10)


# ── extract_last_frame（mock subprocess）────────────────
def test_extract_last_frame_ok(monkeypatch, tmp_path):
    vp = tmp_path / "in.mp4"
    vp.write_bytes(b"video")
    op = tmp_path / "out.jpg"
    seen = []

    class _P:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen.append(list(cmd))
        op.write_bytes(b"\xff\xd8\xff")   # 模拟 ffmpeg 写出末帧
        return _P()

    monkeypatch.setattr(ds.subprocess, "run", fake_run)
    out = ds.extract_last_frame(vp, op)
    assert out == str(op)
    assert seen and str(vp) in seen[0] and seen[0][-1] == str(op)


def test_extract_last_frame_failure(monkeypatch, tmp_path):
    vp = tmp_path / "in.mp4"
    vp.write_bytes(b"v")
    op = tmp_path / "out.jpg"

    class _P:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: _P())
    with pytest.raises(RuntimeError):
        ds.extract_last_frame(vp, op)


# ── workbench_store ──────────────────────────────────────
def test_workbench_store_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(wstore, "WORKBENCH_DIR", tmp_path)
    assert wstore.load_items() == []
    items = [{"id": "a", "kind": "image", "file": "x.png"}]
    wstore.save_items(items)
    assert wstore.load_items() == items
    assert wstore.find_item(items, "a")["file"] == "x.png"
    assert wstore.find_item(items, "zz") is None
    assert wstore.image_path("x.png").parent.name == "images"
    assert wstore.video_path("v.mp4").parent.name == "videos"


# ── _resolve_image_input ─────────────────────────────────
def test_resolve_image_input_passthrough():
    assert wb._resolve_image_input("") == ""
    assert wb._resolve_image_input("http://a/b.png") == "http://a/b.png"
    assert wb._resolve_image_input("data:image/png;base64,xx").startswith("data:")


def test_resolve_image_input_localfile(monkeypatch, tmp_path):
    monkeypatch.setattr(wb.store, "WORKBENCH_DIR", tmp_path)
    (tmp_path / "images").mkdir(parents=True, exist_ok=True)
    (tmp_path / "images" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 50)
    assert wb._resolve_image_input("a.png").startswith("data:image/png;base64,")


def test_resolve_image_input_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(wb.store, "WORKBENCH_DIR", tmp_path)
    with pytest.raises(wb.HTTPException):
        wb._resolve_image_input("nope.png")


# ── gen_video：各模式分支与校验 ──────────────────────────
@pytest.fixture
def wb_env(monkeypatch, tmp_path):
    monkeypatch.setattr(wb.store, "WORKBENCH_DIR", tmp_path)
    captured = {}

    async def fake_submit(model, prompt, media=None, **k):
        captured.update(model=model, prompt=prompt, media=media, **k)
        return {"task_id": "t1", "model": model}

    monkeypatch.setattr(wb.ds, "submit_video_unified", fake_submit)
    return captured


def test_gen_video_t2v(wb_env):
    res = asyncio.run(wb.gen_video({"mode": "t2v", "prompt": "a cat"}))
    assert wb_env["model"] == "wan3.0-video"
    assert wb_env["media"] is None
    assert res["item"]["status"] == "PENDING"
    assert res["item"]["kind"] == "video"


def test_gen_video_i2v(wb_env):
    asyncio.run(wb.gen_video({
        "mode": "i2v", "prompt": "x",
        "first_frame": "data:image/png;base64,AAA", "duration": 5}))
    assert wb_env["model"] == "happyhorse-1.1-i2v"
    assert wb_env["media"] == [{"type": "first_frame", "url": "data:image/png;base64,AAA"}]


def test_gen_video_i2v_requires_first_frame(wb_env):
    with pytest.raises(wb.HTTPException) as ei:
        asyncio.run(wb.gen_video({"mode": "i2v", "prompt": "x"}))
    assert ei.value.status_code == 400


def test_gen_video_r2v(wb_env):
    asyncio.run(wb.gen_video({
        "mode": "r2v", "prompt": "x",
        "refs": ["data:image/png;base64,A", "data:image/png;base64,B"]}))
    assert wb_env["model"] == "happyhorse-1.1-r2v"
    assert len(wb_env["media"]) == 2
    assert wb_env["media"][0]["type"] == "reference_image"


def test_gen_video_r2v_requires_refs(wb_env):
    with pytest.raises(wb.HTTPException) as ei:
        asyncio.run(wb.gen_video({"mode": "r2v", "prompt": "x", "refs": []}))
    assert ei.value.status_code == 400


def test_gen_video_first_last(wb_env):
    asyncio.run(wb.gen_video({
        "mode": "first_last", "prompt": "x",
        "first_frame": "data:image/png;base64,A",
        "last_frame": "data:image/png;base64,B"}))
    assert wb_env["model"] == "wan3.0-video"
    types = [m["type"] for m in wb_env["media"]]
    assert types == ["first_frame", "last_frame"]


def test_gen_video_bad_mode(wb_env):
    with pytest.raises(wb.HTTPException) as ei:
        asyncio.run(wb.gen_video({"mode": "nope", "prompt": "x"}))
    assert ei.value.status_code == 400


# ── seed 透传 ────────────────────────────────
def test_submit_seed(fake_http):
    asyncio.run(ds.submit_video_unified("wan3.0-video", "cat", seed=42))
    assert fake_http["json"]["parameters"]["seed"] == 42


def test_submit_no_seed_by_default(fake_http):
    asyncio.run(ds.submit_video_unified("wan3.0-video", "cat"))
    assert "seed" not in fake_http["json"]["parameters"]


def test_gen_video_seed_subtitle(wb_env):
    res = asyncio.run(wb.gen_video(
        {"mode": "t2v", "prompt": "cat", "seed": 7, "subtitle_text": "你好"}))
    assert wb_env["seed"] == 7
    assert res["item"]["subtitle_text"] == "你好"
    assert res["item"]["params"]["seed"] == 7


# ── burn_subtitle（mock subprocess）──────────────
def test_burn_subtitle_ok(monkeypatch, tmp_path):
    vp = tmp_path / "in.mp4"
    vp.write_bytes(b"video")
    op = tmp_path / "out.mp4"
    seen = {}

    class _P:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        seen["cwd"] = kwargs.get("cwd")
        tf = tmp_path / "in_subtxt.txt"          # 此时尚未被 finally 删除
        if tf.exists():
            seen["text"] = tf.read_text(encoding="utf-8")
        (tmp_path / cmd[-1]).write_bytes(b"out")  # cmd[-1] 为输出裸文件名
        return _P()

    monkeypatch.setattr(ds.subprocess, "run", fake_run)
    monkeypatch.setattr(ds, "find_cjk_font", lambda: "C:/Windows/Fonts/msyh.ttc")
    out = ds.burn_subtitle(vp, "50%\n你好", out_path=op)
    assert out == str(op)
    vf = seen["cmd"][seen["cmd"].index("-vf") + 1]
    assert "drawtext" in vf
    assert "fontfile='C\\:/Windows/Fonts/msyh.ttc'" in vf   # 盘符冒号转义 + 单引号包裹
    assert "textfile=in_subtxt.txt" in vf
    assert seen["cwd"] == str(tmp_path)
    assert seen["text"] == "50%%\n你好"                  # % 转义、换行保留
    assert not (tmp_path / "in_subtxt.txt").exists()      # 临时文本已清理


def test_burn_subtitle_empty_text(tmp_path):
    vp = tmp_path / "in.mp4"
    vp.write_bytes(b"x")
    assert ds.burn_subtitle(vp, "   ") == str(vp)          # 空字幕直接返回原视频


def test_burn_subtitle_no_font(monkeypatch, tmp_path):
    monkeypatch.setattr(ds, "find_cjk_font", lambda: "")
    with pytest.raises(RuntimeError):
        ds.burn_subtitle(tmp_path / "in.mp4", "台词")


# ── 台词表演提示词 ──────────────────────
def test_dialogue_performance_prompt():
    from app.routes import media as md
    out = md._with_dialogue_performance("基础画面", "你走！")
    assert "你走！" in out
    assert "台词表演" in out
    assert "不要出现任何文字" in out
