"""一键生成全部角色形象：跳过已确认 + 全局并发上限。"""
import asyncio

import pytest
from fastapi import HTTPException

from app.routes import media as md


def _char(name, confirmed=False):
    p = {"name": name, "role": "", "visual_description": f"{name}的外貌",
         "image_prompt": f"{name}的立绘", "candidates": [], "confirmed_index": None}
    if confirmed:
        p["image_file"] = f"{name}.png"
        p["candidates"] = [{"file": f"{name}.png", "remote_url": ""}]
        p["confirmed_index"] = 0
    return p


def _patch(monkeypatch, chars, tmp_path, state):
    saved = {}
    monkeypatch.setattr(md.media_store, "load_characters", lambda pid: list(chars))
    monkeypatch.setattr(md.media_store, "save_characters",
                        lambda pid, c: saved.update(chars=c))
    monkeypatch.setattr(md.media_store, "image_path", lambda pid, f: tmp_path / f)

    async def fake_gen(prompt, **kwargs):
        state["active"] += 1
        state["total"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.01)
        state["active"] -= 1
        return "http://example.com/" + prompt

    async def fake_dl(url, path):
        path.write_bytes(b"png")
        return str(path)

    monkeypatch.setattr(md.ds, "gen_one_image_pro", fake_gen)
    monkeypatch.setattr(md.ds, "download_file", fake_dl)
    return saved


def test_candidates_all_skips_confirmed(monkeypatch, tmp_path):
    chars = [_char("甲"), _char("乙", confirmed=True), _char("丙")]
    state = {"active": 0, "peak": 0, "total": 0}
    saved = _patch(monkeypatch, chars, tmp_path, state)

    res = asyncio.run(md.gen_candidates_all("pid", {"count": 3}))

    assert res["total_images"] == 6
    assert [g["index"] for g in res["generated"]] == [0, 2]
    assert [s["index"] for s in res["skipped"]] == [1]
    assert state["total"] == 6
    assert saved["chars"][0]["candidates"]


def test_candidates_all_force_and_concurrency_cap(monkeypatch, tmp_path):
    chars = [_char(f"角色{i}", confirmed=True) for i in range(6)]
    state = {"active": 0, "peak": 0, "total": 0}
    _patch(monkeypatch, chars, tmp_path, state)

    res = asyncio.run(md.gen_candidates_all("pid", {"count": 3, "force": True}))

    assert res["total_images"] == 18
    assert state["total"] == 18
    assert state["peak"] <= md.CANDIDATE_ALL_CONCURRENCY
    assert state["peak"] > 1


def test_candidates_all_all_confirmed_returns_early(monkeypatch, tmp_path):
    chars = [_char("甲", confirmed=True)]
    state = {"active": 0, "peak": 0, "total": 0}
    _patch(monkeypatch, chars, tmp_path, state)

    res = asyncio.run(md.gen_candidates_all("pid", {}))

    assert res["total_images"] == 0
    assert state["total"] == 0
    assert res["skipped"][0]["name"] == "甲"


def test_candidates_all_only_selected_indexes(monkeypatch, tmp_path):
    chars = [_char("甲"), _char("乙"), _char("丙")]
    state = {"active": 0, "peak": 0, "total": 0}
    _patch(monkeypatch, chars, tmp_path, state)

    res = asyncio.run(md.gen_candidates_all("pid", {"count": 3, "indexes": [0, 2]}))

    assert res["total_images"] == 6
    assert [g["index"] for g in res["generated"]] == [0, 2]
    assert state["total"] == 6


def test_candidates_all_rejects_invalid_indexes(monkeypatch, tmp_path):
    chars = [_char("甲")]
    state = {"active": 0, "peak": 0, "total": 0}
    _patch(monkeypatch, chars, tmp_path, state)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(md.gen_candidates_all("pid", {"indexes": [99, "x"]}))

    assert exc.value.status_code == 400