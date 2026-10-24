"""v4：独立「创作工作台」路由（不绑定小说项目）。

提供两大能力：
- 图像：文生图（t2i）/ 图生图（i2i），复用 qwen-image-3.0-pro / wan2.7-image-pro；
- 视频：文生视频（t2v）/ 图生视频首帧（i2v）/ 首尾帧（first_last）/ 参考生视频（r2v），
  走 happyhorse-1.1-i2v / happyhorse-1.1-r2v / wan3.0-video。
所有产物写入全局素材库（workbench_store），可在页面「素材库」回看。
"""
import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.media import workbench_store as store
from app.media import dashscope_media as ds
from app.media import subtitles as subs
from app.config import (WAN3_VIDEO_MODEL, HAPPYHORSE_I2V_MODEL,
                        HAPPYHORSE_R2V_MODEL, REF_IMAGE_MODEL)

router = APIRouter(prefix="/api/workbench")

# 可选模型白名单
IMAGE_MODELS = ["qwen-image-3.0-pro", "wan2.7-image-pro"]
VIDEO_MODELS = [HAPPYHORSE_I2V_MODEL, HAPPYHORSE_R2V_MODEL, WAN3_VIDEO_MODEL]
# 各视频模式的默认模型
MODE_DEFAULT_MODEL = {
    "t2v": WAN3_VIDEO_MODEL,
    "i2v": HAPPYHORSE_I2V_MODEL,
    "first_last": WAN3_VIDEO_MODEL,
    "r2v": HAPPYHORSE_R2V_MODEL,
}
# 视频图像输入上限 20MB，base64 会膨胀，取 18MB 原始字节留余量
_VIDEO_IMG_MAX = 18 * 1024 * 1024


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _img_url(filename: str) -> str:
    return f"/api/workbench/images/{filename}"


def _vid_url(filename: str) -> str:
    return f"/api/workbench/videos/{filename}"


def _detect_ext(data: bytes) -> str:
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:2] == b"BM":
        return "bmp"
    return ""


def _resolve_image_input(val: str) -> str:
    """把前端传来的图片引用解析成 API 可用 url。

    - 空 → ''；http(s)/data: → 原样透传；
    - 否则视为工作台 images/ 下的文件名（或本地路径）→ 读本地转 base64。
    """
    v = (val or "").strip()
    if not v:
        return ""
    if v.startswith(("http://", "https://", "data:")):
        return v
    p = store.image_path(v)
    if not p.exists():
        p = Path(v)
    if p.exists():
        return ds.file_to_data_uri(p, max_bytes=_VIDEO_IMG_MAX)
    raise HTTPException(400, f"图片不存在：{v}")


# ── 素材库：回看 / 删除 ──────────────────────────────────────

@router.get("/items")
async def get_items():
    items = store.load_items()
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"items": items}


@router.delete("/items/{item_id}")
async def delete_item(item_id: str):
    items = store.load_items()
    target = store.find_item(items, item_id)
    if not target:
        raise HTTPException(404, "素材不存在")
    f = target.get("file")
    if f:
        p = (store.video_path(f) if target.get("kind") == "video"
             else store.image_path(f))
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass
    items = [it for it in items if it.get("id") != item_id]
    store.save_items(items)
    return {"ok": True, "id": item_id}


# ── 上传图片（作首帧 / 参考图 / 图生图输入）──────────────────

@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "图片内容为空")
    if len(data) > _VIDEO_IMG_MAX:
        raise HTTPException(400, f"图片过大（{len(data) // 1024}KB），上限 18MB")
    ext = _detect_ext(data)
    if not ext:
        raise HTTPException(400, "不支持的图片格式（仅 png / jpg / webp / bmp）")
    fname = f"wb_upload_{_new_id()}.{ext}"
    store.image_path(fname).write_bytes(data)
    return {"file": fname, "url": _img_url(fname)}


# ── 图像生成：文生图 / 图生图 ────────────────────────────────

@router.post("/image")
async def gen_image(body: dict = None):
    body = body or {}
    mode = (body.get("mode") or "t2i").strip()
    if mode not in ("t2i", "i2i"):
        raise HTTPException(400, "mode 只能是 t2i 或 i2i")
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "请填写提示词")
    model = (body.get("model") or "").strip() or REF_IMAGE_MODEL
    if model not in IMAGE_MODELS:
        model = REF_IMAGE_MODEL
    size = (body.get("size") or "16:9").strip()
    try:
        count = max(1, min(int(body.get("count") or 1), 4))
    except (TypeError, ValueError):
        count = 1

    ref = ""
    if mode == "i2i":
        ref = _resolve_image_input(body.get("ref") or "")
        if not ref:
            raise HTTPException(400, "图生图需要一张参考图（请上传或粘贴图片链接）")

    if mode == "t2i":
        coros = [ds.gen_one_image_pro(prompt, size=size, model=model,
                                      timeout=300, interval=5)
                 for _ in range(count)]
    else:
        coros = [ds.gen_image_with_reference(prompt, reference=ref, size=size,
                                             model=model, timeout=300, interval=5)
                 for _ in range(count)]
    settled = await asyncio.gather(*coros, return_exceptions=True)

    items = store.load_items()
    made, errors = [], []
    for i, r in enumerate(settled, 1):
        if isinstance(r, Exception):
            errors.append(f"第{i}张：{str(r)[:180]}")
            continue
        iid = _new_id()
        fname = f"wb_img_{iid}.png"
        try:
            await ds.download_file(r, store.image_path(fname))
        except Exception as e:
            errors.append(f"第{i}张下载失败：{str(e)[:120]}")
            continue
        item = {"id": iid, "kind": "image", "mode": mode, "model": model,
                "prompt": prompt, "params": {"size": size},
                "file": fname, "url": _img_url(fname), "remote_url": r,
                "status": "DONE", "error": "", "created_at": _now()}
        items.append(item)
        made.append(item)

    if not made:
        raise HTTPException(502, "；".join(errors) or "图像生成失败")
    store.save_items(items)
    return {"items": made, "errors": errors, "count": len(made)}


# ── 从已生成视频抽取末帧（承接长视频）────────────────────────

@router.post("/last-frame")
async def last_frame(body: dict = None):
    body = body or {}
    fname = (body.get("file") or "").strip()
    item_id = (body.get("item_id") or "").strip()
    if not fname and item_id:
        it = store.find_item(store.load_items(), item_id)
        if it and it.get("kind") == "video":
            fname = it.get("file", "")
    if not fname:
        raise HTTPException(400, "请指定要抽取末帧的视频（file 或 item_id）")
    vpath = store.video_path(fname)
    if not vpath.exists():
        raise HTTPException(404, f"视频文件不存在：{fname}")
    out_name = f"wb_lastframe_{_new_id()}.jpg"
    out_path = store.image_path(out_name)
    try:
        await asyncio.to_thread(ds.extract_last_frame, vpath, out_path)
    except Exception as e:
        raise HTTPException(502, f"抽取末帧失败：{e}")
    return {"file": out_name, "url": _img_url(out_name)}


# ── 视频生成：文生视频 / 图生视频 / 首尾帧 / 参考生视频 ────────

@router.post("/video")
async def gen_video(body: dict = None):
    body = body or {}
    mode = (body.get("mode") or "t2v").strip()
    if mode not in MODE_DEFAULT_MODEL:
        raise HTTPException(400, "mode 只能是 t2v / i2v / first_last / r2v")
    model = (body.get("model") or "").strip() or MODE_DEFAULT_MODEL[mode]
    if model not in VIDEO_MODELS:
        model = MODE_DEFAULT_MODEL[mode]
    prompt = (body.get("prompt") or "").strip()
    resolution = (body.get("resolution") or "720P").strip()
    ratio = (body.get("ratio") or "").strip() or None
    try:
        duration = int(body.get("duration") or 5)
    except (TypeError, ValueError):
        duration = 5
    # 按模型能力夹取时长（happyhorse 3–15 / wan3 2–30），并记住是否被调整
    _lo, _hi = ds.model_duration_range(model)
    requested_duration = duration
    if duration != -1:
        duration = max(_lo, min(_hi, duration))
    try:                                            # seed：空/非法则不传（随机）
        seed = int(body.get("seed")) if str(body.get("seed")).strip() not in ("", "None") else None
    except (TypeError, ValueError):
        seed = None
    subtitle_text = (body.get("subtitle_text") or "").strip()   # 可选：字幕/台词文本
    sub_cfg = body.get("subtitles")
    if not (isinstance(sub_cfg, dict) and sub_cfg.get("cues")):
        # 未提供逐句配置时，由字幕文本自动分句定时（按 duration 均分）
        sub_cfg = subs.default_subtitles(subtitle_text, duration) if subtitle_text else None

    # 按模式构造 media
    media = None
    if mode == "t2v":
        if not prompt:
            raise HTTPException(400, "文生视频需要提示词")
    elif mode == "i2v":
        first = _resolve_image_input(body.get("first_frame") or "")
        if not first:
            raise HTTPException(400, "图生视频需要首帧图片（上传/选视频末帧/粘贴链接）")
        media = ds.first_frame_media(first)
    elif mode == "first_last":
        first = _resolve_image_input(body.get("first_frame") or "")
        last = _resolve_image_input(body.get("last_frame") or "")
        if not first or not last:
            raise HTTPException(400, "首尾帧模式需要首帧与尾帧两张图片")
        media = ds.first_last_media(first, last)
    elif mode == "r2v":
        refs = [_resolve_image_input(u) for u in (body.get("refs") or [])]
        refs = [u for u in refs if u]
        if not refs:
            raise HTTPException(400, "参考生视频至少需要 1 张参考图")
        if len(refs) > 9:
            raise HTTPException(400, "参考图最多 9 张")
        media = ds.ref_media(refs)

    try:
        sub = await ds.submit_video_unified(
            model, prompt, media=media, resolution=resolution, ratio=ratio,
            duration=duration, audio=bool(body.get("audio")),
            watermark=False, seed=seed)
    except Exception as e:
        raise HTTPException(502, f"视频任务提交失败：{e}")

    iid = _new_id()
    item = {"id": iid, "kind": "video", "mode": mode, "model": sub["model"],
            "prompt": prompt,
            "params": {"resolution": resolution, "ratio": ratio,
                       "duration": duration, "seed": seed},
            "subtitle_text": subtitle_text,
            "subtitles": sub_cfg,
            "task_id": sub["task_id"], "file": "", "url": "", "remote_url": "",
            "status": "PENDING", "error": "", "created_at": _now()}
    items = store.load_items()
    items.append(item)
    store.save_items(items)
    resp = {"item": item}
    if duration != requested_duration:
        resp["warning"] = (f"请求 {requested_duration}s，{model} 时长范围 "
                           f"{_lo}–{_hi}s，已按 {duration}s 提交")
    return resp


@router.get("/videos")
async def poll_videos():
    """轮询所有未完成的视频任务；成功的下载为本地 mp4。"""
    items = store.load_items()
    changed = False
    for it in items:
        if it.get("kind") != "video":
            continue
        if it.get("status") in ("PENDING", "RUNNING") and it.get("task_id"):
            try:
                out = await ds.get_task(it["task_id"])
                st = out.get("task_status", "UNKNOWN")
                if st == "SUCCEEDED":
                    url = ds.video_url_from_output(out)
                    fname = f"wb_vid_{it['id']}.mp4"
                    await ds.download_file(url, store.video_path(fname))
                    sub_cfg = it.get("subtitles")
                    if isinstance(sub_cfg, dict) and sub_cfg.get("cues"):
                        try:
                            raw = store.video_path(fname)
                            subname = f"wb_vid_{it['id']}_sub.mp4"
                            await asyncio.to_thread(
                                subs.burn_subtitles_timed, raw, sub_cfg,
                                store.video_path(subname))
                            try:
                                raw.unlink()
                            except OSError:
                                pass
                            fname = subname
                        except Exception:
                            pass   # 字幕失败不阻断，保留无字幕视频
                    it.update(status="DONE", file=fname, url=_vid_url(fname),
                              remote_url=url, error="")
                    changed = True
                elif st in ("FAILED", "CANCELLED", "CANCELED", "UNKNOWN_ERROR"):
                    it.update(status="FAILED",
                              error=(out.get("message") or "任务失败")[:200])
                    changed = True
                elif st == "RUNNING" and it.get("status") != "RUNNING":
                    it["status"] = "RUNNING"
                    changed = True
            except Exception as e:
                it.update(status="FAILED", error=str(e)[:200])
                changed = True
    if changed:
        store.save_items(items)
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"items": items}


# ── 文件服务 ────────────────────────────────────────────────

@router.get("/images/{filename}")
async def serve_image(filename: str):
    p = store.image_path(filename)
    if not p.exists():
        raise HTTPException(404, "图片不存在")
    return FileResponse(p)


@router.get("/videos/{filename}")
async def serve_video(filename: str):
    p = store.video_path(filename)
    if not p.exists():
        raise HTTPException(404, "视频不存在")
    return FileResponse(p, media_type="video/mp4", filename=filename)
