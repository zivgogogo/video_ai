"""一键连续生成：顺序执行、尾帧接首帧、失败中止、状态自愈。"""
import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routes import media as md


def _shot(n, dur=5, scene=0):
    return {"shot_number": n, "video_prompt": f"镜头{n}的画面", "dialogue": "",
            "duration_seconds": dur, "scene_index": scene,
            "characters_present": [], "subtitles": None}


def _setup(monkeypatch, tmp_path, shots, fail_on=None):
    """把媒体存储与百炼调用换成内存 + 临时目录版本。"""
    monkeypatch.setattr(md.media_store, "project_dir", lambda pid: tmp_path)
    monkeypatch.setattr(md.media_store, "load_storyboard",
                        lambda pid: [dict(s) for s in shots])
    monkeypatch.setattr(md.media_store, "load_characters", lambda pid: [])
    monkeypatch.setattr(md.media_store, "image_path", lambda pid, f: tmp_path / f)
    monkeypatch.setattr(md.media_store, "video_path", lambda pid, f: tmp_path / f)

    store = {"videos": []}
    monkeypatch.setattr(md.media_store, "load_videos",
                        lambda pid: [dict(v) for v in store["videos"]])

    def fake_save(pid, vids):
        store["videos"] = [dict(v) for v in vids]

    monkeypatch.setattr(md.media_store, "save_videos", fake_save)

    calls, frames = [], []

    async def fake_submit(model, prompt, **kwargs):
        calls.append({"model": model, "prompt": prompt, "media": kwargs.get("media")})
        return {"task_id": f"task{len(calls)}", "model": model}

    async def fake_wait(task_id):
        if fail_on and task_id == fail_on:
            raise RuntimeError("云端生成失败")
        return {"task_status": "SUCCEEDED"}

    async def fake_finalize(pid, v, out):
        fname = f"shot_{v['shot_number']}.mp4"
        (tmp_path / fname).write_bytes(b"mp4")
        v.update(status="DONE", video_file=fname, error="")

    def fake_extract(vpath, out_path):
        frames.append((str(vpath), str(out_path)))
        out_path.write_bytes(b"jpg")
        return str(out_path)

    monkeypatch.setattr(md.ds, "submit_video_unified", fake_submit)
    monkeypatch.setattr(md, "_wait_video_task", fake_wait)
    monkeypatch.setattr(md, "_finalize_video", fake_finalize)
    monkeypatch.setattr(md.ds, "extract_last_frame", fake_extract)
    monkeypatch.setattr(md.ds, "file_to_data_uri",
                        lambda p, **kw: "data:image/jpeg;base64," + Path(p).stem)
    monkeypatch.setattr(md.ds, "first_frame_media", lambda url: [{"image": url}])
    monkeypatch.setattr(md, "_scene_ref_url", lambda pid, idx: "")
    return store, calls, frames


def test_chain_runs_in_order_and_reuses_last_frame(monkeypatch, tmp_path):
    shots = [_shot(1), _shot(2), _shot(3)]
    store, calls, frames = _setup(monkeypatch, tmp_path, shots)

    asyncio.run(md._chain_worker("chain_pid", {"model": md.HAPPYHORSE_R2V_MODEL},
                                 [1, 2, 3]))

    # 严格按镜头号顺序提交
    assert [c["prompt"] for c in calls] == ["镜头1的画面", "镜头2的画面", "镜头3的画面"]
    # 第 1 镜既无首帧也无参考图 → 纯文生视频；第 2/3 镜用上一镜尾帧 → 图生视频
    assert calls[0]["model"] == md.WAN3_VIDEO_MODEL
    assert calls[0]["media"] is None
    assert calls[1]["model"] == md.HAPPYHORSE_I2V_MODEL
    assert calls[1]["media"] == [
        {"image": "data:image/jpeg;base64,shot_2_chain_first"}]
    assert calls[2]["media"] == [
        {"image": "data:image/jpeg;base64,shot_3_chain_first"}]
    # 抽帧来源：第 2 镜抽 shot_1.mp4，第 3 镜抽 shot_2.mp4
    assert [Path(f[0]).name for f in frames] == ["shot_1.mp4", "shot_2.mp4"]

    by_num = {v["shot_number"]: v for v in store["videos"]}
    assert [by_num[n]["status"] for n in (1, 2, 3)] == ["DONE", "DONE", "DONE"]
    state = json.loads((tmp_path / "chain.json").read_text(encoding="utf-8"))
    assert state["active"] is False
    assert state["done"] == 3


def test_chain_uses_manual_first_frame(monkeypatch, tmp_path):
    shots = [_shot(1), _shot(2)]
    _store, calls, frames = _setup(monkeypatch, tmp_path, shots)
    (tmp_path / "manual.png").write_bytes(b"png")
    monkeypatch.setattr(md, "_resolve_project_image",
                        lambda pid, val: "data:image/png;base64,manual")

    asyncio.run(md._chain_worker(
        "chain_pid", {"first_frames": {"1": "manual.png"}}, [1, 2]))

    # 第 1 镜用人工指定的首帧；第 2 镜仍然抽第 1 镜的尾帧
    assert calls[0]["media"] == [{"image": "data:image/png;base64,manual"}]
    assert [Path(f[0]).name for f in frames] == ["shot_1.mp4"]
    assert calls[1]["model"] == md.HAPPYHORSE_I2V_MODEL
    assert calls[1]["media"] == [
        {"image": "data:image/jpeg;base64,shot_2_chain_first"}]


def test_chain_stops_on_failure(monkeypatch, tmp_path):
    shots = [_shot(1), _shot(2), _shot(3)]
    store, calls, _ = _setup(monkeypatch, tmp_path, shots, fail_on="task2")

    asyncio.run(md._chain_worker("chain_pid", {}, [1, 2, 3]))

    by_num = {v["shot_number"]: v for v in store["videos"]}
    assert by_num[1]["status"] == "DONE"
    assert by_num[2]["status"] == "FAILED"
    assert by_num[3]["status"] == "QUEUED"      # 未开始，保持排队态
    state = md.load_chain_state("chain_pid")
    assert state["active"] is False
    assert "镜头2" in state["error"]
    assert len(calls) == 2                      # 第 3 镜没有被提交


def test_chain_state_self_heals_after_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(md.media_store, "project_dir", lambda pid: tmp_path)
    (tmp_path / "chain.json").write_text(
        json.dumps({"active": True, "total": 44, "done": 3, "current": 4}),
        encoding="utf-8")

    state = md.load_chain_state("heal_pid")

    assert state["active"] is False
    assert "中断" in state["error"]
    saved = json.loads((tmp_path / "chain.json").read_text(encoding="utf-8"))
    assert saved["active"] is False


def test_chain_rejects_concurrent_run(monkeypatch):
    class _Busy:
        def done(self):
            return False

    monkeypatch.setitem(md._CHAIN_TASKS, "busy_pid", _Busy())
    with pytest.raises(HTTPException) as ei:
        asyncio.run(md.chain_videos("busy_pid", {}))
    assert ei.value.status_code == 409


def test_chain_rejects_unknown_shots(monkeypatch, tmp_path):
    monkeypatch.setattr(md.media_store, "load_storyboard",
                        lambda pid: [{"shot_number": 1}])
    with pytest.raises(HTTPException) as ei:
        asyncio.run(md.chain_videos("noshot_pid", {"shot_numbers": [99]}))
    assert ei.value.status_code == 400


def test_get_videos_marks_orphan_queue_as_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(md.media_store, "project_dir", lambda pid: tmp_path)
    monkeypatch.setattr(md.media_store, "load_videos", lambda pid: [
        {"shot_number": 5, "status": "QUEUED", "chain": True,
         "task_id": "", "video_file": ""}])
    saved = {}
    monkeypatch.setattr(md.media_store, "save_videos",
                        lambda pid, v: saved.update(videos=v))

    res = asyncio.run(md.get_videos("orphan_pid"))

    assert res["videos"][0]["status"] == "FAILED"
    assert "中断" in res["videos"][0]["error"]
    assert saved["videos"][0]["status"] == "FAILED"