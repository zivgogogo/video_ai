"""v3 媒体路由：角色档案 / 文生角色图（多候选+确认）/ 三视图 / 分镜 / 可灵视频。"""
import asyncio
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Project, StageCache
from app import text_store
from app.media import media_store
from app.media.characters import extract_character_profiles
from app.media.storyboard import generate_storyboard
from app.media import storyboard as sb
from app.media import prompt_elements as pe
from app.media import subtitles as subs
from app.media import dashscope_media as ds
from app.media import voice_media as vm
from app.ai.factory import create_ai_provider, generate_with_pool_fallback
from app.config import (REF_IMAGE_MODEL, EXPORT_DIR, WAN3_VIDEO_MODEL,
                        HAPPYHORSE_I2V_MODEL, HAPPYHORSE_R2V_MODEL,
                        VIDEO_MODEL_DEFAULT, VOICE_MUX_ENABLED)

router = APIRouter(prefix="/api")

# 一次生成的候选图张数
CANDIDATE_COUNT = 3
# 角色立绘用竖构图；三视图用横构图（三个视角并排），1664*928 为 16:9 高清档
PORTRAIT_SIZE = "9:16"
TURNAROUND_SIZE = "1664*928"
# 千问图像3.0旗舰版专用竖构图高清档（9:16）。角色形象图统一改走该尺寸 +
# qwen-image-3.0-pro，取代语义遵循弱、易失真的 wanx 720*1280，画质更专业耐看。
PORTRAIT_SIZE_PRO = "928*1664"
# 可选文生图模型（前端下拉选择；均走 multimodal-generation 接口）
IMAGE_MODEL_CHOICES = ["qwen-image-3.0-pro", "wan2.7-image-pro"]
# 可选视频模型（happyhorse i2v / r2v + wan3.0），默认参考生视频（角色一致性）
VIDEO_MODEL_CHOICES = [HAPPYHORSE_I2V_MODEL, HAPPYHORSE_R2V_MODEL, WAN3_VIDEO_MODEL]
# 视频首帧/参考图 base64 内嵌上限（happyhorse/wan3.0 图像上限 20MB，留余量）
_VIDEO_IMG_MAX = 18 * 1024 * 1024

# 三视图共用的布局/姿态/背景/风格段，普通三视图与场景三视图都拼接使用
_TURNAROUND_LAYOUT = """【三视图布局】
同一画面中水平并排三个全身视角，从左到右依次为：
1. 正面：面向镜头站立，五官清晰可见
2. 正侧面：身体转 90 度，呈现完整侧脸轮廓
3. 背面：完全背对镜头，看不到脸，可见后脑发型与服装背面结构
三个视角大小一致、头顶与脚底对齐同一水平线，视角之间留出间距互不重叠。

【姿态】
站姿自然放松，双臂自然下垂贴于体侧，双腿并拢直立，全身完整入画不裁切。

【背景与光】
纯白色背景，无场景、无道具、无地面阴影；均匀柔和的影棚光，无强烈明暗对比。
画面中不得出现任何文字、标注、箭头、边框或水印。

【风格】
电影感写实风格，高清细节，专业角色设计参考图。"""

# 三视图指令模板。{character_detail} 为七维度外观描述（AI 生成或用户编辑），
# 已确认的形象图会作为参考图一并传入，用于锁定人脸/发型/服装/体型。
TURNAROUND_PROMPT = """以参考图中的人物为唯一依据，绘制该角色的三视图设定表（character turnaround sheet / model sheet）。

【最高优先级：与参考图保持一致】
画面中的人物必须与参考图是同一个人：脸型、五官、发型、发色、肤色、体型、服装款式与颜色、配饰，全部以参考图为准，不得自行更换、美化或重新设计。

【人物外观描述】（与参考图互相印证，两者冲突时以参考图为准）
{character_detail}

""" + _TURNAROUND_LAYOUT

# 场景三视图：人脸锁参考图，服装/道具/状态按章节造型更换
SCENE_TURNAROUND_PROMPT = """以参考图为依据，绘制该角色在指定剧情造型下的三视图设定表（character turnaround sheet）。

【参考图说明】
参考图提供该角色的人脸；若参考图本身已是三视图，则同时沿用它的三视角布局与人物比例。
人脸、五官、脸型、肤色、发型基础形态与发色必须与参考图一致，不得更换或美化。

【换装指令（本图核心）】
把画面中所有视角的服装、鞋子、配饰统一更换为【本章场景造型】描述的同一套。
不得保留参考图原有的任何衣物；左、中、右三个视角必须穿完全相同的一套新服装（同款式、同颜色、同鞋子），严禁混穿。

【角色基础外观】（仅用于人脸与体型）
{base_detail}

【本章场景造型】（本图唯一有效的穿着依据）
{scene_desc}

【配饰与道具】
只画【本章场景造型】中明确提到的配饰与手持物；本章未提及的一律不画。

""" + _TURNAROUND_LAYOUT

# 用 LLM 从章节原文提取角色在本章的造型（服装/道具/状态/发型/神情）
SCENE_LOOK_SYSTEM = ("你是影视服装与造型指导。只输出连贯的中文造型描述，"
                     "不要标题、不要编号、不要解释、不要引号。")

SCENE_LOOK_PROMPT = """阅读以下小说章节片段，针对角色「{name}」，提取TA在本章场景中的造型与身体状态，用于生成该场景下的角色三视图。

依次覆盖五点，连贯成一段，120-180字：
1 本章所穿服装：从内到外逐件写款式、颜色、材质；原文未写时按角色常规着装推断
2 随身物品与道具：本章实际持有或佩戴的
3 身体状态：是否受伤、脏污、淋湿、疲惫、脸色变化
4 发型状态：是否散乱、束起、戴帽、遮挡
5 神情：本章主导的表情与眼神

角色基础设定：{base}

章节标题：{title}
章节片段：
{excerpt}

只写本章可见的外观，不写性格与心理活动。"""

# 用 LLM 把角色档案扩写成七维度外观描述（形态/体型/肤色/着装等）
TURNAROUND_DETAIL_SYSTEM = ("你是影视选角与角色视觉设定师。只输出连贯的中文外观描述文字，"
                            "不要标题、不要编号、不要解释、不要引号。")

TURNAROUND_DETAIL_PROMPT = """根据以下角色资料，写一段用于「三视图」的外观描述。
必须依次覆盖七个维度，每个维度一句话，连贯成一段：
1 脸型与五官：脸型、眼型、眉形、鼻型、唇形与唇色
2 发型与发色：长度、质感、刘海或分缝
3 肤色与肤质：色调、光泽、是否苍白
4 体型与体态：身高感、肩宽、胖瘦、站姿习惯
5 着装：从内到外逐件写清款式、颜色、材质、长度
6 配饰与随身物品：手表、包、首饰等
7 神情气质：常态表情与眼神

角色资料：
外貌设定：{visual_description}
图像提示词：{image_prompt}

要求：150-220 字，只写可见外观，不写性格、心理、剧情。"""


# ── 内部工具 ────────────────────────────────────────────────

def _safe_name(name: str, limit: int = 12) -> str:
    """把角色名清理成可安全用于文件名的片段。"""
    return re.sub(r'[^\w一-鿿]', '', name or '')[:limit] or 'char'


def _local_img_url(project_id: str, filename: str) -> str:
    return f"/api/projects/{project_id}/media/images/{filename}"


def _normalize(profile: dict, project_id: str) -> dict:
    """补齐 v3.1 新增字段，兼容旧数据（老项目只有 6 个基础字段）。"""
    profile.setdefault("name", "")
    profile.setdefault("role", "")
    profile.setdefault("visual_description", "")
    profile.setdefault("image_prompt", "")
    profile.setdefault("image_url", "")
    profile.setdefault("image_file", "")
    profile.setdefault("candidates", [])
    profile.setdefault("confirmed_index", None)
    profile.setdefault("turnaround_file", "")
    profile.setdefault("turnaround_prompt", "")
    profile.setdefault("turnaround_detail", "")
    profile.setdefault("turnaround_prompt_draft", "")
    profile.setdefault("turnaround_model", "")
    profile.setdefault("scene_turnarounds", {})
    profile.setdefault("voice", {})   # v6：角色配音配置（音色/情绪/语速/音调/音量）
    profile.setdefault("updated_at", "")

    # 老数据迁移：已有单图但没有候选列表时，把这张图作为唯一候选并视为已确认
    if profile["image_file"] and not profile["candidates"]:
        profile["candidates"] = [{
            "file": profile["image_file"],
            "remote_url": profile.get("image_url", ""),
            "url": _local_img_url(project_id, profile["image_file"]),
        }]
        profile["confirmed_index"] = 0

    # 候选项补本地访问地址
    for c in profile["candidates"]:
        if c.get("file") and not c.get("url"):
            c["url"] = _local_img_url(project_id, c["file"])

    profile["confirmed"] = (profile.get("confirmed_index") is not None
                            and bool(profile.get("image_file")))
    profile["turnaround_url"] = (_local_img_url(project_id, profile["turnaround_file"])
                                 if profile.get("turnaround_file") else "")
    return profile


def _load(project_id: str, idx: int):
    """加载角色列表并定位到 idx，越界时报 404。返回 (chars, profile)。"""
    chars = media_store.load_characters(project_id)
    if not chars:
        raise HTTPException(404, "还没有角色档案：请先点「提取角色描述」")
    if idx < 0 or idx >= len(chars):
        raise HTTPException(404, f"角色不存在（下标 {idx}，共 {len(chars)} 个）")
    return chars, _normalize(chars[idx], project_id)


def _save(project_id: str, chars: list):
    for c in chars:
        _normalize(c, project_id)
    media_store.save_characters(project_id, chars)


def _clean_llm_text(text: str) -> str:
    """剥掉文本模型偶尔套上的 JSON 外壳（如 {"description": "..."}）。"""
    t = (text or "").strip()
    if t.startswith("{"):
        try:
            obj = json.loads(t)
            if isinstance(obj, dict):
                t = str(obj.get("description") or obj.get("detail")
                        or obj.get("text") or obj.get("scene_desc") or "").strip()
            elif isinstance(obj, list) and obj:
                t = str(obj[0]).strip()
        except (json.JSONDecodeError, TypeError):
            t = t.strip("{}\"' ")
    return t.strip().strip('"').strip("'")


async def _llm_text_with_retry(provider, prompt: str, system: str,
                               attempts: int = 3) -> str:
    """调 LLM 并剥壳，空结果自动重试。

    实测 AI 池偶尔返回空字符串或无法解析的内容（限流/单模型抖动），
    单次调用会把这种偶发失败直接抛给用户，故在这里重试。
    """
    last = ""
    for _ in range(max(1, attempts)):
        try:
            raw = await generate_with_pool_fallback(provider, prompt, system=system)
        except Exception:
            raw = ""
        last = _clean_llm_text(raw)
        if last:
            return last
    return last


def _detect_image_ext(data: bytes) -> str:
    """按 magic bytes 判断图片格式，返回扩展名；不支持返回空串。"""
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:2] == b"BM":
        return "bmp"
    if data[:4] == b"GIF8":
        return "gif"
    return ""


# ── 人物匹配：章节 × 角色 ────────────────────────────────

def _load_aliases(db: Session, project_id: str) -> dict:
    """角色名 -> 别名列表，取自 Stage2 综合人物档案。"""
    row = db.query(StageCache).filter(
        StageCache.project_id == project_id, StageCache.stage == 2).first()
    alias_map = {}
    if row and row.output_json:
        try:
            s2 = json.loads(row.output_json)
        except (json.JSONDecodeError, TypeError):
            s2 = None
        if isinstance(s2, dict):
            for c in s2.get("characters", []):
                if not isinstance(c, dict):
                    continue
                nm = (c.get("name") or "").strip()
                if nm:
                    alias_map[nm] = [a for a in (c.get("aliases") or [])
                                     if a and a != nm]
    return alias_map


def _match_matrix(project_id: str, db: Session) -> list:
    """扫描每章原文，统计每个已建档角色的出现次数（名字 + 别名）。

    用字符串匹配而非 LLM 分析结果，保证“重复出现”的识别可靠且免费。
    """
    chapters = text_store.load_chapters(project_id)
    chars = media_store.load_characters(project_id)
    alias_map = _load_aliases(db, project_id)

    matrix = []
    for ch in chapters:
        content = ch.get("content") or ""
        hits = []
        for i, c in enumerate(chars):
            name = (c.get("name") or "").strip()
            if not name:
                continue
            cnt = 0
            for nm in [name] + alias_map.get(name, []):
                if nm:
                    cnt += content.count(nm)
            if cnt > 0:
                hits.append({"idx": i, "name": name, "count": cnt})
        hits.sort(key=lambda h: -h["count"])
        matrix.append({"chapter_index": ch.get("index"),
                       "title": ch.get("title") or f"第{ch.get('index')}章",
                       "char_count": ch.get("char_count", len(content)),
                       "matches": hits})
    return matrix


def _find_chapter(project_id: str, ci) -> dict:
    try:
        ci = int(ci)
    except (TypeError, ValueError):
        return None
    for ch in text_store.load_chapters(project_id):
        if int(ch.get("index", -1)) == ci:
            return ch
    return None


def _scene_excerpt(content: str, name: str, max_chars: int = 2600) -> str:
    """截取角色名出现位置前后的窗口，供 LLM 聚焦本章造型描写。"""
    windows, total, start = [], 0, 0
    while name:
        i = content.find(name, start)
        if i < 0:
            break
        seg = content[max(0, i - 260): i + 420]
        windows.append(seg)
        total += len(seg)
        start = i + max(1, len(name))
        if total >= max_chars or len(windows) >= 6:
            break
    if not windows:
        return content[:max_chars]
    return "\n……\n".join(windows)


# ── 角色档案：读取 / 提取 / 编辑保存 ─────────────────────────

@router.get("/projects/{project_id}/media/characters")
async def get_characters(project_id: str):
    chars = [_normalize(c, project_id)
             for c in media_store.load_characters(project_id)]
    return {"characters": chars}


@router.post("/projects/{project_id}/media/characters")
async def post_characters(project_id: str, db: Session = Depends(get_db)):
    """AI 提取角色视觉档案（会保留已确认的形象图，不会清空）。"""
    if not db.query(Project).filter(Project.id == project_id).first():
        raise HTTPException(404, "项目不存在")
    try:
        profiles = await extract_character_profiles(db, project_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"characters": [_normalize(p, project_id) for p in profiles]}


@router.put("/projects/{project_id}/media/characters/{idx}")
async def update_character(project_id: str, idx: int, body: dict = None):
    """手动编辑并保存单个角色的文字设定。

    可改字段：name / role / visual_description / image_prompt。
    只更新请求里出现的字段，其余保持原样；不会触碰已生成的图片。
    """
    body = body or {}
    chars, profile = _load(project_id, idx)

    editable = ("name", "role", "visual_description", "image_prompt")
    changed = []
    for k in editable:
        if k in body and body[k] is not None:
            new = str(body[k]).strip()
            if k == "name" and not new:
                raise HTTPException(400, "角色名不能为空")
            if new != profile.get(k, ""):
                profile[k] = new
                changed.append(k)

    # v6：角色配音配置（音色/情绪/语速/音调/音量），规整后保存
    if isinstance(body.get("voice"), dict):
        profile["voice"] = vm.normalize_voice_config(body["voice"])
        if "voice" not in changed:
            changed.append("voice")

    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    chars[idx] = profile
    _save(project_id, chars)

    return {"character": profile, "changed": changed,
            "message": f"已保存（{('、'.join(changed)) or '无变化'}）"}


# ── 候选形象图：一次三张 ────────────────────────────────────

@router.post("/projects/{project_id}/media/characters/{idx}/candidates")
async def gen_candidates(project_id: str, idx: int, body: dict = None):
    """一次生成 3 张候选形象图，供用户挑选。

    不改动已确认的形象；候选结果写入 candidates 字段。
    重新生成会覆盖上一批候选（已确认的那张仍保留在 image_file）。
    """
    body = body or {}
    count = int(body.get("count") or CANDIDATE_COUNT)
    count = max(1, min(count, 4))

    # 前端可选文生图模型；未传/非法则用默认旗舰模型
    model = (body.get("model") or "").strip() or REF_IMAGE_MODEL
    if model not in IMAGE_MODEL_CHOICES:
        model = REF_IMAGE_MODEL

    chars, profile = _load(project_id, idx)
    prompt = (profile.get("image_prompt") or "").strip() \
        or (profile.get("visual_description") or "").strip()
    if not prompt:
        raise HTTPException(400, "该角色缺少图像提示词，请先编辑描述或重新提取")

    try:
        # 角色形象图改用千问图像3.0旗舰版（qwen-image-3.0-pro，走 multimodal 接口）：
        # 相比旧 wanx 纯文生图，五官/发型/服装/光影更专业耐看。
        res = await ds.gen_images_concurrent_pro(prompt, count=count,
                                                 size=PORTRAIT_SIZE_PRO,
                                                 model=model,
                                                 timeout=300, interval=5)
    except Exception as e:
        raise HTTPException(502, f"候选图生成失败：{e}")

    existing = list(profile.get("candidates") or [])
    base = f"char_{idx}_{_safe_name(profile.get('name', ''))}"
    stamp = datetime.now().strftime("%H%M%S")
    start_no = len(existing)          # 序号接续已有草稿，避免文件名/编号重复
    new_cands = []
    for i, remote in enumerate(res["urls"], 1):
        fname = f"{base}_c{start_no + i}_{stamp}.png"
        try:
            await ds.download_file(remote, media_store.image_path(project_id, fname))
        except Exception as e:
            res["errors"].append(f"第{i}张下载失败: {str(e)[:120]}")
            continue
        new_cands.append({"file": fname, "remote_url": remote,
                          "url": _local_img_url(project_id, fname),
                          "model": model})

    if not new_cands:
        raise HTTPException(502, "候选图全部下载失败：" + "；".join(res["errors"]))

    # 累加而非覆盖：保留之前的草稿与已确认的正式形象，直到用户「选中」某张时才清理其余。
    # 新图追加在末尾 → 已确认项下标 confirmed_index 保持不变，仍然有效。
    profile["candidates"] = existing + new_cands
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    chars[idx] = profile
    _save(project_id, chars)

    return {"character": profile, "candidates": profile["candidates"],
            "count": len(new_cands), "total": len(profile["candidates"]),
            "errors": res["errors"], "model": model}


# ── 一键生成全部角色形象（异步并发，全局限 10 张）──────────

CANDIDATE_ALL_CONCURRENCY = 10


async def _gen_candidate_one(project_id: str, prompt: str, fname: str,
                             model: str, sem: asyncio.Semaphore) -> dict:
    """在信号量保护下生成并下载一张候选图（生成+下载共占一个并发槽）。"""
    async with sem:
        remote = await ds.gen_one_image_pro(
            prompt, size=PORTRAIT_SIZE_PRO, model=model, timeout=300, interval=5)
        await ds.download_file(remote, media_store.image_path(project_id, fname))
    return {"file": fname, "remote_url": remote,
            "url": _local_img_url(project_id, fname), "model": model}


async def _gen_candidates_batch(project_id: str, idx: int, profile: dict,
                                count: int, model: str,
                                sem: asyncio.Semaphore) -> dict:
    """为一个角色并发生成 count 张候选（每张占一个信号量槽），不落盘角色档案。"""
    name = (profile.get("name") or "").strip()
    prompt = (profile.get("image_prompt") or "").strip() \
        or (profile.get("visual_description") or "").strip()
    if not prompt:
        return {"index": idx, "name": name, "candidates": [],
                "errors": ["缺少图像提示词，请先编辑描述或重新提取"]}

    base = f"char_{idx}_{_safe_name(name)}"
    stamp = datetime.now().strftime("%H%M%S")
    start_no = len(profile.get("candidates") or [])
    tasks = [
        _gen_candidate_one(project_id, prompt,
                           f"{base}_b{start_no + i}_{stamp}.png", model, sem)
        for i in range(1, count + 1)
    ]
    settled = await asyncio.gather(*tasks, return_exceptions=True)

    cands, errors = [], []
    for i, r in enumerate(settled, 1):
        if isinstance(r, Exception):
            errors.append(f"第{i}张: {str(r)[:150]}")
        else:
            cands.append(r)
    return {"index": idx, "name": name, "candidates": cands, "errors": errors}


@router.post("/projects/{project_id}/media/characters/candidates-all")
async def gen_candidates_all(project_id: str, body: dict = None):
    """一键为多个角色生成候选形象图（异步并发，最多 10 张同时生成）。

    body.indexes 限定只处理哪些角色（前端勾选）；不传则处理全部角色。
    默认只处理「尚未确认形象」的角色；body.force=True 时连已确认的一起重做。
    所有角色 × 所有候选图共享一个 Semaphore(10)，避免一次性打出几十个请求。
    """
    body = body or {}
    try:
        count = int(body.get("count") or CANDIDATE_COUNT)
    except (TypeError, ValueError):
        count = CANDIDATE_COUNT
    count = max(1, min(count, 4))
    model = (body.get("model") or "").strip() or REF_IMAGE_MODEL
    if model not in IMAGE_MODEL_CHOICES:
        model = REF_IMAGE_MODEL
    force = bool(body.get("force"))

    chars = media_store.load_characters(project_id)
    if not chars:
        raise HTTPException(404, "还没有角色档案：请先点「提取角色描述」")

    # 前端勾选的下标（不传 = 全部）；非法值忽略，全部无效则报错
    picked = None
    raw_indexes = body.get("indexes")
    if isinstance(raw_indexes, list) and raw_indexes:
        picked = set()
        for v in raw_indexes:
            try:
                iv = int(v)
            except (TypeError, ValueError):
                continue
            if 0 <= iv < len(chars):
                picked.add(iv)
        if not picked:
            raise HTTPException(400, "indexes 里没有有效的角色下标")

    targets, skipped = [], []
    for idx, raw in enumerate(chars):
        if picked is not None and idx not in picked:
            continue
        profile = _normalize(raw, project_id)
        if not force and profile.get("confirmed"):
            skipped.append({"index": idx, "name": profile.get("name", ""),
                            "reason": "已有确认形象"})
            continue
        targets.append((idx, profile))

    if not targets:
        return {"characters": [_normalize(c, project_id) for c in chars],
                "generated": [], "skipped": skipped, "total_images": 0,
                "concurrency": CANDIDATE_ALL_CONCURRENCY, "model": model}

    sem = asyncio.Semaphore(CANDIDATE_ALL_CONCURRENCY)
    settled = await asyncio.gather(*[
        _gen_candidates_batch(project_id, idx, profile, count, model, sem)
        for idx, profile in targets
    ], return_exceptions=True)

    # 统一在主协程写回，避免多个任务同时改 chars.json
    generated = []
    for (idx, profile), r in zip(targets, settled):
        if isinstance(r, Exception):
            generated.append({"index": idx, "name": profile.get("name", ""),
                              "count": 0, "errors": [str(r)[:150]]})
            continue
        if r["candidates"]:
            profile["candidates"] = (list(profile.get("candidates") or [])
                                     + r["candidates"])
            profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
            chars[idx] = profile
        generated.append({"index": idx, "name": r["name"],
                          "count": len(r["candidates"]), "errors": r["errors"]})
    _save(project_id, chars)

    return {"characters": [_normalize(c, project_id) for c in chars],
            "generated": generated, "skipped": skipped,
            "total_images": sum(g["count"] for g in generated),
            "concurrency": CANDIDATE_ALL_CONCURRENCY, "model": model}


@router.post("/projects/{project_id}/media/characters/{idx}/confirm")
async def confirm_character(project_id: str, idx: int, body: dict = None):
    """从候选图中确认一张作为正式形象，可随时改选另一张。

    确认后同步更新 image_file / image_url —— 视频生成（omni 角色一致性）
    依赖 image_url 作为参考图，因此必须一起写入。
    """
    body = body or {}
    chars, profile = _load(project_id, idx)
    cands = profile.get("candidates") or []
    if not cands:
        raise HTTPException(400, "还没有候选图：请先生成 3 张候选")

    ci = body.get("index", body.get("candidate_index"))
    if ci is None:
        raise HTTPException(400, "缺少参数 index（要确认第几张，从 0 开始）")
    try:
        ci = int(ci)
    except (TypeError, ValueError):
        raise HTTPException(400, "index 必须是整数")
    if ci < 0 or ci >= len(cands):
        raise HTTPException(400, f"index 超出范围（共 {len(cands)} 张候选）")

    picked = cands[ci]
    picked_file = picked.get("file", "")

    # 选中即「保存」：删掉其余所有草稿图文件（含上一张正式形象），只留选中的这张，
    # 这样反复生成→挑选的循环里草稿不会越堆越多、白占磁盘。
    removed = 0
    for j, c in enumerate(cands):
        if j == ci:
            continue
        f = c.get("file")
        if not f or f == picked_file:
            continue
        try:
            p = media_store.image_path(project_id, f)
            if p.exists():
                p.unlink()
            removed += 1
        except OSError:
            pass

    # 候选收敛为选中的这一张，confirmed_index 归 0
    kept = {"file": picked_file, "remote_url": picked.get("remote_url", ""),
            "url": _local_img_url(project_id, picked_file)}
    if picked.get("imported"):
        kept["imported"] = True
    profile["candidates"] = [kept]
    profile["confirmed_index"] = 0
    profile["image_file"] = picked_file
    profile["image_url"] = picked.get("remote_url", "")
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")

    # 形象换了，旧的三视图不再匹配，清空以免误用
    if profile.get("turnaround_file"):
        profile["turnaround_file"] = ""
        profile["turnaround_prompt"] = ""

    chars[idx] = profile
    _save(project_id, chars)

    return {"character": profile,
            "image_url": _local_img_url(project_id, picked_file),
            "removed": removed,
            "message": f"已保存为正式形象，并清理了 {removed} 张其余草稿"}


# ── 三视图 ──────────────────────────────────────────────────

@router.post("/projects/{project_id}/media/characters/{idx}/turnaround")
async def gen_turnaround(project_id: str, idx: int, body: dict = None):
    """生成角色三视图（正面/侧面/背面）。必须先确认正式形象。

    与旧版的本质区别：把已确认的形象图作为参考图（base64 内嵌）传给
    qwen-image-3.0-pro 的图像编辑模式，由模型“照着这张图改朝向”，
    从而锁住人脸、发型、服装与体型；旧版 wanx-v1 纯文生图会自由发挥导致失真。
    """
    body = body or {}
    chars, profile = _load(project_id, idx)

    if profile.get("confirmed_index") is None or not profile.get("image_file"):
        raise HTTPException(400, "请先从 3 张候选中确认一张形象，再生成三视图")

    ref_path = media_store.image_path(project_id, profile["image_file"])
    if not ref_path.exists():
        raise HTTPException(404, f"已确认的形象图文件不存在：{profile['image_file']}")

    # 提示词优先级：本次传入 > 已保存草稿 > 默认模板+现有描述
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        prompt = (profile.get("turnaround_prompt_draft") or "").strip()
    if not prompt:
        detail = (profile.get("turnaround_detail") or "").strip() \
            or (profile.get("visual_description") or "").strip() \
            or (profile.get("image_prompt") or "").strip()
        prompt = TURNAROUND_PROMPT.format(character_detail=detail or "（无）")

    try:
        remote = await ds.gen_image_with_reference(
            prompt, reference=ref_path, size=TURNAROUND_SIZE,
            timeout=300, interval=5)
        fname = f"char_{idx}_{_safe_name(profile.get('name',''))}_turnaround.png"
        await ds.download_file(remote, media_store.image_path(project_id, fname))
    except Exception as e:
        raise HTTPException(502, f"三视图生成失败：{e}")

    profile["turnaround_file"] = fname
    profile["turnaround_remote_url"] = remote
    profile["turnaround_prompt"] = prompt
    profile["turnaround_model"] = REF_IMAGE_MODEL
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    chars[idx] = profile
    _save(project_id, chars)

    return {"character": profile,
            "turnaround_url": _local_img_url(project_id, fname),
            "model": REF_IMAGE_MODEL,
            "message": "三视图已生成（参考图锁脸）"}


@router.post("/projects/{project_id}/media/characters/{idx}/turnaround-prompt")
async def gen_turnaround_prompt(project_id: str, idx: int, body: dict = None):
    """用 LLM 依据角色档案生成七维度外观描述，并组装成完整三视图提示词。

    覆盖：脸型五官 / 发型发色 / 肤色 / 体型体态 / 着装 / 配饰 / 神情气质。
    结果存入 turnaround_prompt_draft，前端编辑框可直接再改。
    """
    chars, profile = _load(project_id, idx)

    visual = (profile.get("visual_description") or "").strip()
    imgp = (profile.get("image_prompt") or "").strip()
    if not visual and not imgp:
        raise HTTPException(400, "角色描述为空，请先编辑描述或重新提取角色描述")

    provider = create_ai_provider()
    detail = await _llm_text_with_retry(
        provider,
        TURNAROUND_DETAIL_PROMPT.format(visual_description=visual or "（无）",
                                        image_prompt=imgp or "（无）"),
        TURNAROUND_DETAIL_SYSTEM)
    if not detail:
        raise HTTPException(502, "AI 未返回有效的外观描述（已自动重试多次）")

    prompt = TURNAROUND_PROMPT.format(character_detail=detail)
    profile["turnaround_detail"] = detail
    profile["turnaround_prompt_draft"] = prompt
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    chars[idx] = profile
    _save(project_id, chars)

    return {"detail": detail, "prompt": prompt,
            "message": "已按七个维度生成外观描述，可在编辑框中继续修改"}


# ── 人物匹配 + 章节场景三视图 ────────────────────────────

@router.get("/projects/{project_id}/media/scene-match")
async def get_scene_match(project_id: str, db: Session = Depends(get_db)):
    """人物匹配：扫描每章原文，列出每个已建档角色的出场次数。

    纯字符串匹配（名字+别名），不调 AI、不花钱。
    同时返回每个角色已生成的场景三视图，供前端直接回显。
    """
    chars = media_store.load_characters(project_id)
    if not chars:
        raise HTTPException(400, "还没有角色档案：请先提取角色描述")
    if not text_store.load_chapters(project_id):
        raise HTTPException(400, "还没有章节数据：请先导入小说文本")

    matrix = _match_matrix(project_id, db)
    return {
        "matrix": matrix,
        "characters": [{"idx": i,
                        "name": c.get("name", ""),
                        "confirmed": bool(c.get("image_file")),
                        "scene_turnarounds": c.get("scene_turnarounds") or {}}
                       for i, c in enumerate(chars)],
    }


@router.post("/projects/{project_id}/media/characters/{idx}/scene-desc")
async def gen_scene_desc(project_id: str, idx: int, body: dict = None,
                         db: Session = Depends(get_db)):
    """LLM 提取角色在指定章节的造型描述（服装/道具/状态/发型/神情）。"""
    body = body or {}
    chars, profile = _load(project_id, idx)
    ci = body.get("chapter_index")
    if ci is None:
        raise HTTPException(400, "缺少参数 chapter_index")
    ch = _find_chapter(project_id, ci)
    if not ch:
        raise HTTPException(404, f"章节不存在：{ci}")

    excerpt = _scene_excerpt(ch.get("content") or "", profile.get("name", ""))
    base = (profile.get("visual_description") or "").strip() \
        or (profile.get("image_prompt") or "").strip()
    provider = create_ai_provider()
    look = await _llm_text_with_retry(
        provider,
        SCENE_LOOK_PROMPT.format(name=profile.get("name", ""),
                                 base=base or "（无）",
                                 title=ch.get("title", ""),
                                 excerpt=excerpt),
        SCENE_LOOK_SYSTEM)
    if not look:
        raise HTTPException(502, "AI 未返回有效的造型描述（已自动重试多次）")

    st = profile.setdefault("scene_turnarounds", {})
    entry = st.setdefault(str(int(ci)), {})
    entry["chapter_index"] = int(ci)
    entry["chapter_title"] = ch.get("title", "")
    entry["scene_desc"] = look
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    chars[idx] = profile
    _save(project_id, chars)

    return {"scene_desc": look, "chapter_index": int(ci),
            "message": "已提取本章造型，可编辑后生成三视图"}


@router.post("/projects/{project_id}/media/characters/{idx}/scene-turnaround")
async def gen_scene_turnaround(project_id: str, idx: int, body: dict = None):
    """生成角色在指定章节造型下的三视图：参考图锁脸 + 按本章造型换装。"""
    body = body or {}
    chars, profile = _load(project_id, idx)
    ci = body.get("chapter_index")
    if ci is None:
        raise HTTPException(400, "缺少参数 chapter_index")

    if profile.get("confirmed_index") is None or not profile.get("image_file"):
        raise HTTPException(400, "请先确认一张正式形象，再生成场景三视图")

    # 优先用已生成的基础三视图作参考图：它本身就是三视角布局，
    # 模型只需统一换装，比用单张正面图更容易保持三视角服装一致。
    ref_name = profile.get("turnaround_file") or profile.get("image_file")
    ref_path = media_store.image_path(project_id, ref_name)
    if not ref_path.exists():
        raise HTTPException(404, f"参考图文件不存在：{ref_name}")

    st = profile.get("scene_turnarounds") or {}
    entry = st.get(str(int(ci))) or {}
    scene_desc = (body.get("scene_desc") or "").strip() \
        or (entry.get("scene_desc") or "").strip()
    if not scene_desc:
        raise HTTPException(400, "还没有本章造型描述：请先点「提取造型」")

    base_detail = (profile.get("turnaround_detail") or "").strip() \
        or (profile.get("visual_description") or "").strip() \
        or (profile.get("image_prompt") or "").strip()

    prompt = (body.get("prompt") or "").strip() \
        or SCENE_TURNAROUND_PROMPT.format(
            base_detail=base_detail or "（无）", scene_desc=scene_desc)

    try:
        remote = await ds.gen_image_with_reference(
            prompt, reference=ref_path, size=TURNAROUND_SIZE,
            timeout=300, interval=5)
        fname = (f"char_{idx}_{_safe_name(profile.get('name', ''))}"
                 f"_ch{int(ci)}_scene.png")
        await ds.download_file(remote, media_store.image_path(project_id, fname))
    except Exception as e:
        raise HTTPException(502, f"场景三视图生成失败：{e}")

    ch = _find_chapter(project_id, ci)
    entry.update({"chapter_index": int(ci),
                  "chapter_title": (ch or {}).get("title", entry.get("chapter_title", "")),
                  "scene_desc": scene_desc,
                  "file": fname,
                  "prompt": prompt,
                  "model": REF_IMAGE_MODEL,
                  "created_at": datetime.now().isoformat(timespec="seconds")})
    st[str(int(ci))] = entry
    profile["scene_turnarounds"] = st
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    chars[idx] = profile
    _save(project_id, chars)

    return {"character": profile, "entry": entry,
            "scene_url": _local_img_url(project_id, fname),
            "model": REF_IMAGE_MODEL,
            "message": f"第{int(ci)}章场景三视图已生成"}


# ── 人物形象导入 ────────────────────────────────────────

@router.post("/projects/{project_id}/media/characters/{idx}/import-image")
async def import_character_image(project_id: str, idx: int,
                                 file: UploadFile = File(None),
                                 url: str = Form(None),
                                 as_confirmed: bool = Form(True)):
    """导入已确认好的人物形象图（从其他工具/素材库来的图）。

    两种来源二选一：
    - file：multipart 上传的图片文件（png/jpg/webp/bmp/gif，≤10MB）
    - url ：公网图片链接，会下载存本地并保留远程地址

    as_confirmed=True（默认）直接设为正式形象；False 则只加入候选列表。
    注意：本地上传的图没有公网链接，可灵视频的角色一致性参考将不可用
    （三视图/场景三视图走本地 base64，不受影响）；如需视频一致性请改用 url 方式。
    """
    chars, profile = _load(project_id, idx)

    data, remote_url = b"", ""
    if file is not None and file.filename:
        data = await file.read()
    elif (url or "").strip():
        remote_url = url.strip()
        if not remote_url.startswith(("http://", "https://")):
            raise HTTPException(400, "url 必须是 http/https 公网链接")
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
                r = await c.get(remote_url)
                r.raise_for_status()
                data = r.content
        except Exception as e:
            raise HTTPException(502, f"下载图片失败：{e}")
    else:
        raise HTTPException(400, "请上传图片文件，或提供公网图片链接")

    if not data:
        raise HTTPException(400, "图片内容为空")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, f"图片过大（{len(data) // 1024}KB），上限 10MB")
    ext = _detect_image_ext(data)
    if not ext:
        raise HTTPException(400, "不支持的图片格式（仅 png / jpg / webp / bmp / gif）")

    stamp = datetime.now().strftime("%H%M%S")
    fname = (f"char_{idx}_{_safe_name(profile.get('name', ''))}"
             f"_import_{stamp}.{ext}")
    media_store.image_path(project_id, fname).write_bytes(data)

    cands = profile.setdefault("candidates", [])
    cands.append({"file": fname, "remote_url": remote_url,
                  "url": _local_img_url(project_id, fname), "imported": True})
    ci = len(cands) - 1

    warning = ""
    if as_confirmed:
        profile["confirmed_index"] = ci
        profile["image_file"] = fname
        profile["image_url"] = remote_url
        # 形象换了，旧的三视图/场景三视图不再匹配，清空以免误用
        profile["turnaround_file"] = ""
        profile["turnaround_prompt"] = ""
        profile["scene_turnarounds"] = {}
        if not remote_url:
            warning = ("本地导入的形象没有公网链接，视频角色一致性暂不可用；"
                       "三视图与场景三视图不受影响。如需视频一致性请用公网链接导入。")
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    chars[idx] = profile
    _save(project_id, chars)

    return {"character": profile, "candidate_index": ci,
            "image_url": _local_img_url(project_id, fname),
            "confirmed": bool(as_confirmed), "warning": warning,
            "message": ("形象已导入并设为正式形象" if as_confirmed
                        else "形象已导入到候选列表")}


# ── 文生角色图（旧接口，保留兼容）────────────────────────────

@router.post("/projects/{project_id}/media/characters/{idx}/image")
async def gen_character_image(project_id: str, idx: int):
    """旧版单图生成接口，保留以兼容既有调用。新流程请用 /candidates + /confirm。"""
    chars, profile = _load(project_id, idx)
    prompt = profile.get("image_prompt") or profile.get("visual_description")
    if not prompt:
        raise HTTPException(400, "该角色缺少图像提示词，请先提取角色描述")

    try:
        remote_url = await ds.gen_one_image_pro(prompt, size=PORTRAIT_SIZE_PRO,
                                                timeout=300, interval=5)
        filename = f"char_{idx}_{_safe_name(profile['name'])}.png"
        await ds.download_file(remote_url,
                               media_store.image_path(project_id, filename))
    except Exception as e:
        raise HTTPException(502, f"角色图生成失败：{e}")

    profile["image_url"] = remote_url
    profile["image_file"] = filename
    profile["confirmed_index"] = 0
    profile["candidates"] = [{"file": filename, "remote_url": remote_url,
                              "url": _local_img_url(project_id, filename)}]
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    chars[idx] = profile
    _save(project_id, chars)

    return {"character": profile,
            "image_url": _local_img_url(project_id, filename)}


@router.get("/projects/{project_id}/media/images/{filename}")
async def serve_image(project_id: str, filename: str):
    p = media_store.image_path(project_id, filename)
    if not p.exists():
        raise HTTPException(404, "图片不存在")
    return FileResponse(p, media_type="image/png")


# ── v6：角色配音（CosyVoice 语音合成 + 音画混流）──────────────

@router.get("/projects/{project_id}/media/audio/{filename}")
async def serve_audio(project_id: str, filename: str):
    """提供配音/试听音频文件访问。"""
    p = media_store.audio_path(project_id, filename)
    if not p.exists():
        raise HTTPException(404, "音频不存在")
    return FileResponse(p, media_type="audio/mpeg")


@router.get("/projects/{project_id}/media/voices")
async def get_voices(project_id: str):
    """配音选项：分类音色库 + 情感 + 参数范围 + 默认值；附各角色已存声音配置。"""
    char_voices = {}
    for c in media_store.load_characters(project_id):
        nm = (c.get("name") or "").strip()
        if nm:
            char_voices[nm] = c.get("voice") or {}
    return {**vm.voice_options(), "character_voices": char_voices}


@router.post("/projects/{project_id}/media/voice-preview")
async def voice_preview(project_id: str, body: dict = None):
    """试听：用给定声音配置合成一小段样本，返回可播放的音频 URL。"""
    body = body or {}
    text = (body.get("text") or "").strip() or "你好，这是角色配音试听。"
    text = text[:200]
    raw_cfg = body.get("voice") if isinstance(body.get("voice"), dict) else body
    cfg = vm.normalize_voice_config(raw_cfg)
    fname = f"preview_{_safe_name(cfg['voice'])}_{datetime.now().strftime('%H%M%S%f')}.mp3"
    out = media_store.audio_path(project_id, fname)
    try:
        await asyncio.to_thread(vm.synthesize, text, out, **cfg)
    except Exception as e:
        raise HTTPException(502, f"试听合成失败：{e}")
    return {"url": f"/api/projects/{project_id}/media/audio/{fname}",
            "file": fname, "config": cfg}


@router.post("/projects/{project_id}/media/storyboard/{shot_number}/voice-gen")
async def gen_shot_voice(project_id: str, shot_number: int, body: dict = None):
    """为镜头每句台词（字幕 cue）生成配音，按时间轴记录 voice_tracks，供视频混流。

    - 每句按 speaker 找角色声音配置（无则用默认/传入配置）；cue.voice 可单句覆盖；
    - 音频存 media/{pid}/audio/shot{n}_cue{i}_*.mp3；记录 start（取自 cue）与实际时长。
    """
    body = body or {}
    shots = media_store.load_storyboard(project_id)
    shot = _find_shot(shots, shot_number)
    if not shot:
        raise HTTPException(404, f"镜头不存在（#{shot_number}）")
    cues = (shot.get("subtitles") or {}).get("cues") or []
    if not cues:
        raise HTTPException(400, "该镜头没有台词字幕，无法配音（请先在字幕里配置台词）")

    char_voice = {}
    for c in media_store.load_characters(project_id):
        nm = (c.get("name") or "").strip()
        if nm:
            char_voice[nm] = vm.normalize_voice_config(c.get("voice") or {})
    default_cfg = vm.normalize_voice_config(body.get("voice") or {})
    only = body.get("cue_indexes")
    old_tracks = {t.get("index"): t for t in (shot.get("voice_tracks") or [])}

    tracks, errors = [], []
    for i, cue in enumerate(cues):
        text = (cue.get("zh") or "").strip()
        if not text:
            continue
        if only is not None and i not in only:
            if i in old_tracks:
                tracks.append(old_tracks[i])
            continue
        speaker = (cue.get("speaker") or "").strip()
        cfg = dict(char_voice.get(speaker) or default_cfg)
        if isinstance(cue.get("voice"), dict) and cue["voice"]:
            cfg = vm.normalize_voice_config({**cfg, **cue["voice"]})
        fname = f"shot{shot_number}_cue{i}_{_safe_name(speaker)}.mp3"
        out = media_store.audio_path(project_id, fname)
        try:
            await asyncio.to_thread(vm.synthesize, text, out, **cfg)
            dur = await asyncio.to_thread(vm.probe_audio_duration, out)
            tracks.append({"index": i, "speaker": speaker, "text": text,
                           "file": fname,
                           "url": f"/api/projects/{project_id}/media/audio/{fname}",
                           "start": float(cue.get("start") or 0),
                           "duration": round(dur or 0, 2),
                           "voice": cfg["voice"]})
        except Exception as e:
            errors.append(f"第{i + 1}句：{str(e)[:150]}")
    tracks.sort(key=lambda t: t.get("start", 0))
    shot["voice_tracks"] = tracks
    shot["updated_at"] = datetime.now().isoformat(timespec="seconds")
    media_store.save_storyboard(project_id, shots)
    return {"shot_number": shot_number, "tracks": tracks,
            "errors": errors, "count": len(tracks)}


@router.post("/projects/{project_id}/media/storyboard/{shot_number}/auto-beats")
async def auto_beats(project_id: str, shot_number: int, body: dict = None):
    """v6：AI 自动把镜头拆成时间轴分段（beats），写回并重算 video_prompt。"""
    body = body or {}
    shots = media_store.load_storyboard(project_id)
    shot = _find_shot(shots, shot_number)
    if not shot:
        raise HTTPException(404, f"镜头不存在（#{shot_number}）")
    try:
        beats = await sb.gen_beats_for_shot(shot, body.get("duration"))
    except Exception as e:
        raise HTTPException(502, f"AI 自动分时失败：{e}")
    if not beats:
        raise HTTPException(502, "AI 未返回有效的时间分段，请重试或手动添加")
    shot["beats"] = beats
    shot["video_prompt"] = pe.assemble_video_prompt(shot.get("elements") or {}, beats)
    shot["updated_at"] = datetime.now().isoformat(timespec="seconds")
    media_store.save_storyboard(project_id, shots)
    return {"shot_number": shot_number, "beats": beats,
            "video_prompt": shot["video_prompt"]}


# ── 分镜 prompt ─────────────────────────────────────────────

@router.get("/projects/{project_id}/media/storyboard")
async def get_storyboard(project_id: str):
    return {"shots": media_store.load_storyboard(project_id)}


@router.post("/projects/{project_id}/media/storyboard")
async def post_storyboard(project_id: str, body: dict = None,
                          db: Session = Depends(get_db)):
    if not db.query(Project).filter(Project.id == project_id).first():
        raise HTTPException(404, "项目不存在")
    body = body or {}
    try:
        shots = await generate_storyboard(
            db, project_id,
            shots_per_scene=body.get("shots_per_scene") or 4,
            max_scenes=body.get("max_scenes"),
            protect_confirmed=body.get("protect_confirmed", True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    scene_count = len({s.get("scene_title") for s in shots})
    protected = sum(1 for s in shots if s.get("confirmed"))
    return {"shots": shots, "scene_count": scene_count, "protected": protected}


@router.put("/projects/{project_id}/media/storyboard")
async def put_storyboard(project_id: str, body: dict = None):
    """保存手动编辑后的分镜列表（查看/编辑/保存闭环的保存端）。

    会重排 shot_number 并校验每个镜头都有 video_prompt
    （视频生成与角色匹配都依赖它），避免存坏数据。
    """
    body = body or {}
    shots = body.get("shots")
    if not isinstance(shots, list) or not shots:
        raise HTTPException(400, "shots 必须是非空数组")

    clean = []
    for i, s in enumerate(shots, 1):
        if not isinstance(s, dict):
            raise HTTPException(400, f"第{i}个镜头格式错误（应为对象）")
        s = dict(s)
        s["shot_number"] = i
        if not (s.get("video_prompt") or "").strip():
            raise HTTPException(400, f"镜头{i} 缺少 video_prompt（视频生成依赖它）")
        clean.append(s)

    media_store.save_storyboard(project_id, clean)
    return {"shots": clean, "count": len(clean),
            "message": f"已保存 {len(clean)} 个分镜"}


# ── v5：Prompt 中心（剧本↔分镜一一对应 / 结构化要素 / 编辑确认）──

STRUCTURIZE_SYSTEM = "你是资深分镜师与摄影指导。只输出合法 JSON，不要其他文字。"

STRUCTURIZE_PROMPT = """把一个已有分镜镜头拆解为结构化专业要素。依据镜头现有信息，从候选选项里为每个要素挑选最贴切的值（也可保留更贴切的自定义文本），不要臆造新剧情。

【镜头现有信息】
景别 / 运镜：{shot_size} / {camera_angle}
画面描述：{frame}
角色动作：{action}
台词：{dialogue}
出场角色：{chars}
现有视频 Prompt：{video_prompt}

【角色外观设定】（subject 需用它锚定角色外观，禁止“一名男子/年轻女子”等模糊指代）
{appearances}

【专业要素候选】
{options_menu}

只输出 JSON：{{"elements":{{"subject":"","action":"","dialogue":"","scene":"","environment":"","shot_type":"","shot_size":"","camera_angle":"","focal_length":"","camera_movement":"","composition":"","time_of_day":"","light_source":"","lighting":[],"color_tone":"","contrast":"","mood":"","emotion":"","visual_style":"","quality":[]}}}}"""


def _merge_elements(shot: dict, els_raw: dict) -> dict:
    """把要素并入 shot：补全骨架、兜底风格/画质、重算汇总与顶层兼容字段。"""
    base = pe.new_elements()
    cur = shot.get("elements")
    if isinstance(cur, dict):
        for k, v in cur.items():
            if k in base:
                base[k] = v
    for k, v in (els_raw or {}).items():
        if k in base and v not in (None, "", []):
            base[k] = v
    if not base.get("visual_style"):
        base["visual_style"] = "电影感写实"
    if not base.get("quality"):
        base["quality"] = ["电影级", "高清"]
    shot["elements"] = base
    shot["video_prompt"] = pe.assemble_video_prompt(base, shot.get("beats"))
    shot["ai_image_prompt"] = pe.assemble_image_prompt(base)
    shot["dialogue"] = base.get("dialogue", "")
    shot["character_action"] = base.get("action", "")
    shot["shot_size"] = base.get("shot_size", "")
    shot["camera_angle"] = " ".join(x for x in [base.get("camera_angle", ""),
                                               base.get("camera_movement", "")] if x)
    shot["frame_description"] = " ".join(x for x in [base.get("scene", ""),
                                                     base.get("environment", "")] if x)
    return shot


def _stage4_scenes(db: Session, project_id: str) -> list:
    """读取 Stage4 结构化场景，供 Prompt 中心展示“剧本/脚本”侧并做场↔镜映射。"""
    row = db.query(StageCache).filter(
        StageCache.project_id == project_id, StageCache.stage == 4).first()
    scenes = []
    if row and row.output_json:
        try:
            s4 = json.loads(row.output_json)
        except (json.JSONDecodeError, TypeError):
            s4 = None
        if isinstance(s4, list):
            for i, sc in enumerate(s4):
                if not isinstance(sc, dict):
                    continue
                scenes.append({
                    "index": i,
                    "act": sc.get("act", 1), "episode": sc.get("episode", 1),
                    "sequence": sc.get("sequence", i + 1),
                    "title": sc.get("scene_heading") or sc.get("location") or f"场景{i + 1}",
                    "scene_heading": sc.get("scene_heading", ""),
                    "location": sc.get("location", ""), "time": sc.get("time", ""),
                    "setting": sc.get("setting_description", ""),
                    "characters": sc.get("characters_present", []) or [],
                    "script_text": sb._render_scene_content(sc.get("content")),
                })
    return scenes


def _find_shot(shots: list, shot_number: int):
    for s in shots:
        if s.get("shot_number") == shot_number:
            return s
    return None


def _norm_title(s) -> str:
    """归一化场名/镜头标题用于匹配：去掉括号/标点/分隔符（含·）与空白。"""
    return re.sub(r"[\s\[\]【】（）()：:，,。.、·•・/\\|｜\-—–~!！?？<>《》]", "", s or "")


def _lcs_ratio(a: str, b: str) -> float:
    """字符级最长公共子序列 / 较短串长度（对中文短标题的模糊匹配够用）。"""
    if not a or not b:
        return 0.0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            cur[j] = prev[j - 1] + 1 if ai == b[j - 1] else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1] / min(len(a), len(b))


def _resolve_shot_scenes(shots: list, scenes: list) -> bool:
    """为缺 scene_index 的镜头按标题稳健匹配场序，返回是否有变更。

    AI 常把 scene_title 写成缩写/改写（如“苏青鱼公寓” vs 场“苏青鱼租住的公寓”），
    故分三级匹配：归一化精确 → 包含 → LCS 相似度（阈值 0.6），同时比对
    location/title/scene_heading。仍未匹配的镜头由前端归入“未归类”。
    """
    if not scenes or not shots:
        return False
    lookup = {}
    for sc in scenes:
        for key in (sc.get("title"), sc.get("location"), sc.get("scene_heading")):
            nk = _norm_title(key)
            if nk and nk not in lookup:
                lookup[nk] = sc["index"]
    changed = False
    for sh in shots:
        if isinstance(sh.get("scene_index"), int) and 0 <= sh["scene_index"] < len(scenes):
            continue
        st = _norm_title(sh.get("scene_title"))
        if not st:
            continue
        idx = lookup.get(st)
        if idx is None:                       # 包含匹配
            for nk, si in lookup.items():
                if st in nk or nk in st:
                    idx = si
                    break
        if idx is None:                       # LCS 相似度兜底（AI 改写标题）
            best, best_score = None, 0.0
            for sc in scenes:
                for key in (sc.get("location"), sc.get("title"), sc.get("scene_heading")):
                    score = _lcs_ratio(st, _norm_title(key))
                    if score > best_score:
                        best_score, best = score, sc["index"]
            if best is not None and best_score >= 0.6:
                idx = best
        if idx is not None:
            sh["scene_index"] = idx
            changed = True
    return changed


@router.get("/projects/{project_id}/media/prompt-center")
async def get_prompt_center(project_id: str, db: Session = Depends(get_db)):
    """Prompt 中心数据：剧本(场) + 分镜(镜) + 统计 + 要素选项。"""
    shots = media_store.load_storyboard(project_id)
    scenes = _stage4_scenes(db, project_id)
    # 为旧/已结构化但无 scene_index 的镜头稳健回填场序（持久化，稳定映射）
    if _resolve_shot_scenes(shots, scenes):
        media_store.save_storyboard(project_id, shots)
    confirmed = sum(1 for s in shots if s.get("confirmed"))
    structured = sum(1 for s in shots
                     if isinstance(s.get("elements"), dict) and s.get("elements"))
    chars = media_store.load_characters(project_id)
    char_voices = {(c.get("name") or "").strip(): (c.get("voice") or {})
                   for c in chars if (c.get("name") or "").strip()}
    return {
        "stats": {"scenes": len(scenes), "shots": len(shots),
                  "confirmed": confirmed, "structured": structured},
        "scenes": scenes, "shots": shots,
        "element_options": pe.ELEMENT_OPTIONS,
        "text_elements": pe.TEXT_ELEMENTS,
        "negative_rules": pe.NEGATIVE_RULES,
        "scene_refs": media_store.load_scene_refs(project_id),
        "character_names": [c.get("name") for c in chars if c.get("name")],
        # v6：配音（音色库 + 情感 + 参数范围 + 各角色已存声音配置）
        "voice_options": vm.voice_options(),
        "character_voices": char_voices,
    }


@router.post("/projects/{project_id}/media/scenes/{scene_index}/ref-image")
async def gen_scene_ref(project_id: str, scene_index: int, body: dict = None,
                        db: Session = Depends(get_db)):
    """为某场生成"场景参考图"（无人空镜/建立镜头），锁定该场所有镜头的场景一致性。"""
    body = body or {}
    scenes = _stage4_scenes(db, project_id)
    sc = next((s for s in scenes if s["index"] == scene_index), None)
    if not sc:
        raise HTTPException(404, f"场景不存在（{scene_index}）")
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        loc = sc.get("location") or sc.get("title") or ""
        time_ = sc.get("time") or ""
        setting = sc.get("setting") or ""
        prompt = (f"电影感写实场景建立镜头（空镜，画面中不要出现任何人物/角色）：{loc}，{time_}。{setting} "
                  "清晰展现该场景的空间结构、陈设、材质、光线与氛围，作为该场所有镜头统一的场景参考；"
                  "35mm 电影质感，构图完整，画面干净通透，无文字无水印。")
    try:
        remote = await ds.gen_one_image_pro(prompt, size="16:9",
                                            model=REF_IMAGE_MODEL, timeout=300, interval=5)
        fname = f"sceneref_{scene_index}.png"
        await ds.download_file(remote, media_store.image_path(project_id, fname))
    except Exception as e:
        raise HTTPException(502, f"场景图生成失败：{e}")
    refs = media_store.load_scene_refs(project_id)
    refs[str(scene_index)] = {"file": fname, "url": _local_img_url(project_id, fname),
                              "prompt": prompt,
                              "created_at": datetime.now().isoformat(timespec="seconds")}
    media_store.save_scene_refs(project_id, refs)
    return {"scene_index": scene_index, "ref": refs[str(scene_index)]}


@router.post("/projects/{project_id}/media/scenes/{scene_index}/ref-image/upload")
async def upload_scene_ref(project_id: str, scene_index: int,
                           file: UploadFile = File(...)):
    """上传自定义场景参考图。"""
    data = await file.read()
    if not data:
        raise HTTPException(400, "图片内容为空")
    if len(data) > _VIDEO_IMG_MAX:
        raise HTTPException(400, f"图片过大（{len(data) // 1024}KB），上限 18MB")
    ext = _detect_image_ext(data)
    if not ext:
        raise HTTPException(400, "不支持的图片格式（仅 png/jpg/webp/bmp）")
    fname = f"sceneref_{scene_index}.{ext}"
    media_store.image_path(project_id, fname).write_bytes(data)
    refs = media_store.load_scene_refs(project_id)
    refs[str(scene_index)] = {"file": fname, "url": _local_img_url(project_id, fname),
                              "prompt": "",
                              "created_at": datetime.now().isoformat(timespec="seconds")}
    media_store.save_scene_refs(project_id, refs)
    return {"scene_index": scene_index, "ref": refs[str(scene_index)]}


@router.delete("/projects/{project_id}/media/scenes/{scene_index}/ref-image")
async def delete_scene_ref(project_id: str, scene_index: int):
    """清除某场的场景参考图。"""
    refs = media_store.load_scene_refs(project_id)
    ref = refs.pop(str(scene_index), None)
    if ref and ref.get("file"):
        try:
            p = media_store.image_path(project_id, ref["file"])
            if p.exists():
                p.unlink()
        except OSError:
            pass
    media_store.save_scene_refs(project_id, refs)
    return {"ok": True, "scene_index": scene_index}


@router.put("/projects/{project_id}/media/storyboard/{shot_number}")
async def update_shot(project_id: str, shot_number: int, body: dict = None):
    """保存单镜结构化要素/文本/汇总；据 elements 重算 video_prompt（除非 override）。"""
    body = body or {}
    shots = media_store.load_storyboard(project_id)
    shot = _find_shot(shots, shot_number)
    if not shot:
        raise HTTPException(404, f"镜头不存在（#{shot_number}）")
    # v6：画面时间轴（时间戳分段）——先规整存入，供 video_prompt 汇总用
    if isinstance(body.get("beats"), list):
        _dur = body.get("duration_seconds", shot.get("duration_seconds"))
        shot["beats"] = pe.normalize_beats(body["beats"], _dur)
    if isinstance(body.get("elements"), dict):
        _merge_elements(shot, body["elements"])
    elif isinstance(body.get("beats"), list):
        # 只改了时间轴也要按最新要素+beats 重算汇总
        shot["video_prompt"] = pe.assemble_video_prompt(
            shot.get("elements") or {}, shot.get("beats"))
    if "duration_seconds" in body:
        try:
            shot["duration_seconds"] = int(body["duration_seconds"]) or 5
        except (TypeError, ValueError):
            pass
    if isinstance(body.get("characters_present"), list):
        shot["characters_present"] = body["characters_present"]
    if isinstance(body.get("subtitles"), dict):
        shot["subtitles"] = body["subtitles"]   # 逐句字幕配置（时间/中英/说话人/位置/双语）
    if body.get("override") and (body.get("video_prompt") or "").strip():
        shot["video_prompt"] = body["video_prompt"].strip()
    shot["updated_at"] = datetime.now().isoformat(timespec="seconds")
    media_store.save_storyboard(project_id, shots)
    return {"shot": shot}


@router.post("/projects/{project_id}/media/storyboard/{shot_number}/split")
async def split_shot(project_id: str, shot_number: int, body: dict = None):
    """把对白过长的镜头按句拆成多个镜头。

    继承场景/角色/视觉要素，把台词与逐句字幕按时长权重分配到各段，
    每段沿用原时长并重排字幕时间；拆分后全局重编号（后续镜头号顺延）。
    """
    body = body or {}
    shots = media_store.load_storyboard(project_id)
    idx = next((i for i, s in enumerate(shots)
                if s.get("shot_number") == shot_number), None)
    if idx is None:
        raise HTTPException(404, f"镜头不存在（#{shot_number}）")
    shot = shots[idx]
    duration = shot.get("duration_seconds", 5) or 5

    # 取 cues：已编辑的 subtitles 优先，否则由台词分句
    sub = shot.get("subtitles")
    if isinstance(sub, dict) and sub.get("cues"):
        cues = sub["cues"]
    else:
        names = [c.get("name") for c in media_store.load_characters(project_id)
                 if c.get("name")]
        dlg = shot.get("dialogue") or (shot.get("elements") or {}).get("dialogue") or ""
        cues = subs.split_dialogue_to_cues(dlg, duration, names)
    if len(cues) < 2:
        raise HTTPException(400, "对白不足两句，无法拆分")

    parts = body.get("parts") or subs.suggest_split_count(cues, duration)
    try:
        parts = int(parts)
    except (TypeError, ValueError):
        parts = 2
    parts = max(2, min(parts, len(cues)))
    groups = subs.distribute_cues(cues, parts)

    base_el = dict(shot.get("elements") or {})
    parts_dialogue = ["".join((c.get("zh") or "") for c in g) for g in groups]
    # 可选：AI 为每段重配贴合各自台词的画面要素（人物/场景/画风保持一致）
    refined = [None] * len(groups)
    if body.get("ai"):
        try:
            refined = await sb.refine_split_parts(
                shot.get("scene_title", ""), base_el,
                shot.get("characters_present", []), parts_dialogue)
        except Exception:
            refined = [None] * len(groups)

    new_shots = []
    for gi, group in enumerate(groups):
        el = dict(refined[gi]) if isinstance(refined[gi], dict) else dict(base_el)
        dlg_text = parts_dialogue[gi]
        el["dialogue"] = dlg_text
        part_cues = subs._assign_timing(
            [{"start": 0.0, "end": 0.0, "zh": c.get("zh", ""),
              "en": c.get("en", ""), "speaker": c.get("speaker", "")} for c in group],
            duration)
        ns = dict(shot)
        ns.pop("shot_number", None)
        ns.pop("confirmed", None)
        ns["elements"] = el
        ns["dialogue"] = dlg_text
        ns["duration_seconds"] = duration
        ns["subtitles"] = {**(shot.get("subtitles") or {}), "enabled": True,
                           "cues": part_cues}
        ns["video_prompt"] = pe.assemble_video_prompt(el)
        new_shots.append(ns)

    shots[idx:idx + 1] = new_shots
    for i, s in enumerate(shots, 1):
        s["shot_number"] = i
    media_store.save_storyboard(project_id, shots)
    return {"ok": True, "added": len(new_shots), "total": len(shots),
            "from": idx + 1, "to": idx + len(new_shots)}


@router.post("/projects/{project_id}/media/storyboard/{shot_number}/confirm")
async def confirm_shot(project_id: str, shot_number: int, body: dict = None):
    """切换镜头确认状态（确认后视为定稿）。"""
    body = body or {}
    shots = media_store.load_storyboard(project_id)
    shot = _find_shot(shots, shot_number)
    if not shot:
        raise HTTPException(404, f"镜头不存在（#{shot_number}）")
    conf = body.get("confirmed")
    conf = (not shot.get("confirmed")) if conf is None else bool(conf)
    shot["confirmed"] = conf
    shot["confirmed_at"] = datetime.now().isoformat(timespec="seconds") if conf else ""
    media_store.save_storyboard(project_id, shots)
    return {"shot_number": shot_number, "confirmed": conf}


@router.post("/projects/{project_id}/media/storyboard/reassemble/{shot_number}")
async def reassemble_shot(project_id: str, shot_number: int, body: dict = None):
    """按要素实时重算汇总 prompt（预览用，不落盘）。"""
    body = body or {}
    els = body.get("elements")
    if not isinstance(els, dict):
        shot = _find_shot(media_store.load_storyboard(project_id), shot_number)
        els = (shot or {}).get("elements") or {}
    return {"video_prompt": pe.assemble_video_prompt(els),
            "ai_image_prompt": pe.assemble_image_prompt(els)}


@router.post("/projects/{project_id}/media/storyboard/structurize")
async def structurize_storyboard(project_id: str, body: dict = None,
                                 db: Session = Depends(get_db)):
    """旧分镜“AI 一键结构化解析”：把段落式 video_prompt 拆成结构化要素再汇总。

    默认只处理缺 elements 的镜头；force=true 时全部重解析。逐镜并发（Semaphore 3）。
    """
    body = body or {}
    force = bool(body.get("force"))
    shots = media_store.load_storyboard(project_id)
    if not shots:
        raise HTTPException(400, "还没有分镜：请先生成分镜 Prompt")
    todo = [s for s in shots
            if force or not (isinstance(s.get("elements"), dict) and s.get("elements"))]
    if not todo:
        return {"parsed": 0, "failed": 0, "total": len(shots),
                "message": "所有镜头已是结构化，无需解析"}

    appearances = sb._appearances(db, project_id)
    options_menu = sb._options_menu()
    provider = create_ai_provider()
    sem = asyncio.Semaphore(3)

    async def _one(shot: dict) -> bool:
        prompt = STRUCTURIZE_PROMPT.format(
            shot_size=shot.get("shot_size", "") or "（未指定）",
            camera_angle=shot.get("camera_angle", "") or "（未指定）",
            frame=shot.get("frame_description", "") or "（无）",
            action=shot.get("character_action", "") or "（无）",
            dialogue=shot.get("dialogue", "") or "（无）",
            chars="、".join(shot.get("characters_present", []) or []) or "（未指定）",
            video_prompt=(shot.get("video_prompt", "") or "")[:1500],
            appearances=appearances, options_menu=options_menu)
        async with sem:
            try:
                raw = await generate_with_pool_fallback(
                    provider, prompt, system=STRUCTURIZE_SYSTEM, output_format="json")
            except Exception:
                return False
        data = sb.extract_json(raw) or {}
        els = data.get("elements") if isinstance(data.get("elements"), dict) else data
        if not isinstance(els, dict) or not els:
            return False
        _merge_elements(shot, els)
        shot["structured_at"] = datetime.now().isoformat(timespec="seconds")
        return True

    results = await asyncio.gather(*[_one(s) for s in todo])
    parsed = sum(1 for r in results if r)
    media_store.save_storyboard(project_id, shots)
    return {"parsed": parsed, "failed": len(todo) - parsed, "total": len(shots),
            "message": f"已结构化解析 {parsed}/{len(todo)} 个镜头"
                       + (f"（{len(todo) - parsed} 个失败，可重试）" if parsed < len(todo) else "")}


# ── 视频生成 ────────────────────────────────────────────────

def _resolve_project_image(project_id: str, val: str) -> str:
    """把前端传入的图片引用解析成视频接口可用 url。

    支持：空 → ''；http(s)/data: → 原样；项目 images/ 下文件名或本地路径 → base64。
    """
    v = (val or "").strip()
    if not v:
        return ""
    if v.startswith(("http://", "https://", "data:")):
        return v
    p = media_store.image_path(project_id, v)
    if not p.exists():
        p = Path(v)
    if p.exists():
        return ds.file_to_data_uri(p, max_bytes=_VIDEO_IMG_MAX)
    raise HTTPException(400, f"首帧图片不存在：{v}")


def _char_image_ref(project_id: str, c: dict) -> str:
    """取单个角色的参考图 url（本地形象图转 base64 优先，回退公网 url），无则空串。"""
    f = c.get("image_file")
    if f:
        p = media_store.image_path(project_id, f)
        if p.exists():
            try:
                return ds.file_to_data_uri(p, max_bytes=_VIDEO_IMG_MAX)
            except Exception:
                return c.get("image_url") or ""
        return c.get("image_url") or ""
    return c.get("image_url") or ""


def _char_refs_named(project_id: str, shot: dict, char_map: dict, limit: int = 8):
    """返回 ([(name,url)], [无图角色名])：仅含有可用参考图的角色，保持出场顺序。"""
    named, imageless = [], []
    for name in shot.get("characters_present", []):
        c = char_map.get(name)
        if not c:
            imageless.append(name)
            continue
        url = _char_image_ref(project_id, c)
        if url:
            if len(named) < limit:
                named.append((name, url))
        else:
            imageless.append(name)
    return named, imageless


def _img_token(model: str, n: int) -> str:
    """参考图指代 token：happyhorse 用 [Image n]，wan3.0 用 图n。"""
    return f"图{n}" if str(model).startswith("wan3") else f"[Image {n}]"


def _scene_ref_url(project_id: str, scene_index) -> str:
    """取某场的场景参考图（base64），无则空串。"""
    if scene_index is None:
        return ""
    ref = media_store.load_scene_refs(project_id).get(str(scene_index))
    if not ref or not ref.get("file"):
        return ""
    p = media_store.image_path(project_id, ref["file"])
    if not p.exists():
        return ""
    try:
        return ds.file_to_data_uri(p, max_bytes=_VIDEO_IMG_MAX)
    except Exception:
        return ""


def _build_reference_media(project_id: str, shot: dict, char_map: dict,
                           model: str, char_limit: int = 8, use_scene: bool = True):
    """构造参考生视频的 media + 绑定前缀（角色图在前=[Image 1..N]，场景图放最后）。

    角色优先：把角色参考图放在靠前的主参考位，场景图放最后（仍绑定，但权重更低），
    避免"无人空镜占据 [Image 1] 主参考位"稀释人物一致性。use_scene=False 时不注入场景图。
    返回 (media_urls, prompt_prefix)；绑定前缀把每张参考图与角色名/场景显式对应，
    解决"传了参考图但模型不知道哪张是谁"导致的角色/场景串味。
    """
    named, imageless = _char_refs_named(project_id, shot, char_map, limit=char_limit)
    media_urls, binding = [], []
    n = 0
    for name, url in named:                       # 角色图优先占主参考位
        n += 1
        media_urls.append(url)
        binding.append(f"{_img_token(model, n)}={name}")
    has_scene = False
    if use_scene:
        sref = _scene_ref_url(project_id, shot.get("scene_index"))
        if sref:
            n += 1
            media_urls.append(sref)               # 场景图放最后（次参考位）
            binding.append(f"{_img_token(model, n)}=场景/环境")
            has_scene = True
    prefix = ""
    if binding:
        prefix = "参考图绑定：" + "，".join(binding) + "。"
        if imageless:
            prefix += f"（{'、'.join(imageless)} 无参考图，按文字描述出现。）"
        prefix += "请严格保持每个角色的五官/发型/服装与其对应参考图一致，同一角色跨镜头不得变化"
        prefix += "；场景空间/陈设/光线与场景参考图保持一致。\n" if has_scene else "。\n"
    return media_urls, prefix



async def _resolve_first_frame(project_id: str, num, first_frames: dict,
                               cont: bool, prev_num, done_file: dict) -> str:
    """解析某镜头的首帧：手动指定优先，其次「承接上一镜头末帧」（自动抽帧）。"""
    ref = first_frames.get(str(num))
    if ref is None:
        ref = first_frames.get(num)
    if ref:
        return _resolve_project_image(project_id, ref)
    if cont and prev_num is not None:
        vf = done_file.get(prev_num)
        if vf:
            vpath = media_store.video_path(project_id, vf)
            if vpath.exists():
                out = media_store.image_path(project_id, f"shot_{num}_firstframe.jpg")
                await asyncio.to_thread(ds.extract_last_frame, vpath, out)
                return ds.file_to_data_uri(out, max_bytes=_VIDEO_IMG_MAX)
    return ""


def _with_dialogue_performance(prompt: str, dialogue: str) -> str:
    """把台词融入视频 prompt：让角色开口说话（口型/表情/肢体），且画面不生成文字。

    无声视频下，口型与情绪表演是“看见对话”的关键；真正的台词文字由
    后期 burn_subtitle 烧录为清晰字幕，故这里明确要求模型不要在画面里写字。
    """
    return (f"{prompt}\n\n【台词表演】本镜头台词：{dialogue}。"
            "请让说话角色自然开口，口型开合与语气节奏匹配，配合情绪化的表情、眼神与肢体语言"
            "（争吵时激烈、内心独白时内敛、自言自语时低声）。画面中不要出现任何文字、字幕或标注。")


@router.post("/projects/{project_id}/media/videos")
async def post_videos(project_id: str, body: dict = None):
    """提交分镜视频任务（happyhorse i2v/r2v 或 wan3.0）。

    body 可选：shot_numbers / force / model / resolution / ratio / duration /
    first_frames({shot_number: 图片引用}) / continuation(承接上一镜头末帧)。
    - r2v：取镜头出场角色形象作参考图（角色一致性）；
    - i2v：需首帧（手动指定或承接）；
    - wan3.0：有首帧走首帧/首尾帧，无首帧走纯文生视频。
    """
    shots = media_store.load_storyboard(project_id)
    if not shots:
        raise HTTPException(400, "还没有分镜：请先生成分镜 prompt")
    body = body or {}
    selected = body.get("shot_numbers") or [s["shot_number"] for s in shots]
    model = (body.get("model") or "").strip() or VIDEO_MODEL_DEFAULT
    if model not in VIDEO_MODEL_CHOICES:
        model = VIDEO_MODEL_DEFAULT
    resolution = (body.get("resolution") or "720P").strip()
    ratio = (body.get("ratio") or "").strip() or None
    cont = bool(body.get("continuation"))
    first_frames = body.get("first_frames") or {}
    body_dur = body.get("duration")
    audio = bool(body.get("audio"))                 # 默认无声（项目偏好）
    pext = body.get("prompt_extend")                # 仅 wan3.0 生效
    pext = None if pext is None else bool(pext)
    try:                                            # seed：空/非法则不传（随机）
        seed = int(body.get("seed")) if str(body.get("seed")).strip() not in ("", "None") else None
    except (TypeError, ValueError):
        seed = None
    subtitle_on = bool(body.get("subtitle"))         # 烧录台词字幕
    dlg_prompt_on = bool(body.get("dialogue_prompt"))  # 把台词融入表演提示
    use_scene = bool(body.get("scene_ref", True))     # 是否注入场景参考图（默认开，可关以最大化人物权重）

    char_map = {c.get("name"): c for c in media_store.load_characters(project_id)}
    all_char_names = [n for n in char_map.keys() if n]   # 全部已知角色名，供字幕识别说话人
    videos = media_store.load_videos(project_id)
    done_nums = {v["shot_number"] for v in videos if v.get("status") == "DONE"}
    done_file = {v["shot_number"]: v.get("video_file")
                 for v in videos if v.get("status") == "DONE"}

    results, errors, skipped = [], [], []
    warns = []                       # 时长被模型上限夹取等非致命提示
    force = bool(body.get("force"))
    prev_num = None
    for shot in shots:
        num = shot["shot_number"]
        if num in selected and num in done_nums and not force:
            skipped.append(num)          # 已完成且未强制重做 → 跳过（前端会提示）
        elif num in selected:
            prompt = shot.get("video_prompt", "") or ""
            dialogue = (shot.get("dialogue") or "").strip()
            if dlg_prompt_on and dialogue:
                prompt = _with_dialogue_performance(prompt, dialogue)
            dur = int(body_dur or shot.get("duration_seconds", 5) or 5)
            # 提前按模型能力夹取：字符串时间轴、提交参数都用夹取后的值
            lo, hi = ds.model_duration_range(model)
            if dur != -1:
                clamped = max(lo, min(hi, dur))
                if clamped != dur:
                    warns.append(f"镜头{num}: 请求 {dur}s，{model} 时长范围 {lo}–{hi}s，已按 {clamped}s 提交")
                    dur = clamped
            # 字幕：优先用镜头已编辑的逐句配置，否则由台词自动分句定时
            sub_cfg = None
            if subtitle_on:
                sc = shot.get("subtitles")
                if isinstance(sc, dict) and sc.get("cues"):
                    sub_cfg = sc
                elif dialogue:
                    speakers = list(dict.fromkeys(
                        (shot.get("characters_present") or []) + all_char_names))
                    sub_cfg = subs.default_subtitles(dialogue, dur, speakers)
            try:
                first_ref, last_ref, media = "", "", None
                if model == HAPPYHORSE_R2V_MODEL:
                    media_urls, prefix = _build_reference_media(
                        project_id, shot, char_map, model, char_limit=8,
                        use_scene=use_scene)
                    if not media_urls:
                        raise RuntimeError("该镜头无可用的角色/场景参考图，无法用参考生视频（请先确认角色形象或生成场景参考图，或改用其他模型）")
                    media = ds.ref_media(media_urls)
                    prompt = prefix + prompt
                elif model == HAPPYHORSE_I2V_MODEL:
                    first_ref = await _resolve_first_frame(
                        project_id, num, first_frames, cont, prev_num, done_file)
                    if not first_ref:
                        raise RuntimeError("图生视频需要首帧：请为镜头%d指定首帧图片，或开启「承接上一镜头」且上一镜头已生成完成" % num)
                    media = ds.first_frame_media(first_ref)
                elif model.startswith("wan3"):
                    first_ref = await _resolve_first_frame(
                        project_id, num, first_frames, cont, prev_num, done_file)
                    last_ref = _resolve_project_image(
                        project_id, first_frames.get(f"{num}_last") or "")
                    if first_ref and last_ref:
                        media = ds.first_last_media(first_ref, last_ref)
                    elif first_ref:
                        media = ds.first_frame_media(first_ref)
                    else:
                        # 纯文生视频：若有角色/场景参考图，改用参考模式提升一致性
                        media_urls, prefix = _build_reference_media(
                            project_id, shot, char_map, model, char_limit=9,
                            use_scene=use_scene)
                        if media_urls:
                            media = ds.ref_media(media_urls[:10])
                            prompt = prefix + prompt
                        else:
                            media = None
                    if not media and not prompt:
                        raise RuntimeError("文生视频需要视频 Prompt")

                sub = await ds.submit_video_unified(
                    model, prompt, media=media, resolution=resolution,
                    ratio=ratio, duration=dur, audio=audio,
                    prompt_extend=pext, watermark=False, seed=seed)
                videos = [v for v in videos if v["shot_number"] != num]
                videos.append({"shot_number": num, "task_id": sub["task_id"],
                               "model": sub["model"], "status": "PENDING",
                               "video_file": "", "error": "", "subtitles": sub_cfg})
                results.append(num)
            except HTTPException as e:
                errors.append(f"镜头{num}: {e.detail}")
            except Exception as e:
                errors.append(f"镜头{num}: {e}")
        prev_num = num
    media_store.save_videos(project_id, videos)
    return {"submitted": results, "errors": errors, "skipped": skipped,
            "warnings": warns, "videos": videos, "model": model}


# ── 一键连续生成：上一镜头尾帧 = 下一镜头首帧 ─────────────

_CHAIN_TASKS: dict = {}       # project_id -> asyncio.Task（同时只允许一个）
CHAIN_POLL_INTERVAL = 5       # 轮询云端任务间隔（秒）
CHAIN_TIMEOUT = 1800          # 单个镜头最长等待（秒）


def _chain_state_path(project_id: str):
    return media_store.project_dir(project_id) / "chain.json"


def load_chain_state(project_id: str) -> dict:
    """读取连续生成进度（刷新页面后仍能看到跑到第几个镜头）。

    服务重启后内存里的 _CHAIN_TASKS 丢失，这里把残留的 active 标记自愈为中断，
    避免前端永远等待一个已经不存在的任务。
    """
    p = _chain_state_path(project_id)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}
    if data.get("active") and project_id not in _CHAIN_TASKS:
        data["active"] = False
        if not data.get("error"):
            data["error"] = "服务已重启，连续生成中断"
        try:
            _save_chain_state(project_id, data)
        except OSError:
            pass
    return data


def _save_chain_state(project_id: str, state: dict):
    _chain_state_path(project_id).write_text(
        json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _save_chain_videos(project_id: str, videos: list) -> None:
    """链式 worker 落盘：链内镜头以内存为准，其他镜头以磁盘为准。

    连续生成会跑很久，期间用户可能又单独提交/重做别的镜头；直接整表覆盖盘
    上其他镜头的最新状态会丢提交，所以先把它们从磁盘合并回来。
    """
    on_disk = {v.get("shot_number"): v for v in media_store.load_videos(project_id)}
    merged, seen = [], set()
    for v in videos:
        n = v.get("shot_number")
        if v.get("chain") or n not in on_disk:
            merged.append(v)
        else:
            merged.append(on_disk[n])
        seen.add(n)
    for n, cur in on_disk.items():
        if n not in seen:
            merged.append(cur)
    media_store.save_videos(project_id, merged)


async def _finalize_video(project_id: str, v: dict, out: dict) -> None:
    """云端任务成功：下载 mp4 → 烧字幕 → 混配音，并把结果写回 v。"""
    url = ds.video_url_from_output(out)
    fname = f"shot_{v['shot_number']}.mp4"
    await ds.download_file(url, media_store.video_path(project_id, fname))
    sub_cfg = v.get("subtitles")
    if isinstance(sub_cfg, dict) and sub_cfg.get("cues"):
        try:
            raw = media_store.video_path(project_id, fname)
            subname = f"shot_{v['shot_number']}_sub.mp4"
            await asyncio.to_thread(
                subs.burn_subtitles_timed, raw, sub_cfg,
                media_store.video_path(project_id, subname))
            try:
                raw.unlink()
            except OSError:
                pass
            fname = subname
        except Exception:
            pass   # 字幕失败不阻断，保留无字幕视频
    # v6：混入角色配音（若该镜头已生成配音且开启混流）
    if VOICE_MUX_ENABLED:
        try:
            sb_shot = _find_shot(
                media_store.load_storyboard(project_id), v["shot_number"])
            tracks = (sb_shot or {}).get("voice_tracks") or []
            segs = [{"audio": str(media_store.audio_path(project_id, t["file"])),
                     "start": t.get("start", 0)}
                    for t in tracks if t.get("file")]
            if segs:
                vname = f"shot_{v['shot_number']}_voiced.mp4"
                await asyncio.to_thread(
                    vm.mux_voice_to_video,
                    media_store.video_path(project_id, fname), segs,
                    media_store.video_path(project_id, vname))
                fname = vname
        except Exception:
            pass   # 配音混流失败不阻断，保留字幕/无声版
    v.update(status="DONE", video_file=fname, error="")


async def _wait_video_task(task_id: str) -> dict:
    """轮询云端任务直到成功；失败/超时抛 RuntimeError。"""
    waited = 0
    while waited < CHAIN_TIMEOUT:
        try:
            out = await ds.get_task(task_id)
        except Exception:
            await asyncio.sleep(CHAIN_POLL_INTERVAL)
            waited += CHAIN_POLL_INTERVAL
            continue
        st = out.get("task_status", "UNKNOWN")
        if st == "SUCCEEDED":
            return out
        if st in ("FAILED", "CANCELLED", "UNKNOWN_ERROR"):
            raise RuntimeError(out.get("message", "任务失败")[:200])
        await asyncio.sleep(CHAIN_POLL_INTERVAL)
        waited += CHAIN_POLL_INTERVAL
    raise RuntimeError("生成超时")


async def _submit_chain_shot(project_id: str, shot: dict, body: dict,
                             char_map: dict, prev_file: str) -> dict:
    """为连续生成提交单个镜头。

    首帧优先级：手动指定 > 上一镜头末帧 > 本场场景参考图；
    有首帧走图生视频（wan3 保持 wan3，其余用 happyhorse-i2v）；
    无首帧时：r2v 有参考图就用参考生视频，否则 wan3 纯文生视频。
    """
    num = shot["shot_number"]
    prompt = shot.get("video_prompt", "") or ""
    dialogue = (shot.get("dialogue") or "").strip()
    if body.get("dialogue_prompt") and dialogue:
        prompt = _with_dialogue_performance(prompt, dialogue)

    # 1) 首帧：手动 > 上一镜头末帧 > 本场场景参考图
    first_ref = ""
    first_frames = body.get("first_frames") or {}
    manual = first_frames.get(str(num)) or first_frames.get(num)
    if manual:
        first_ref = _resolve_project_image(project_id, manual)
    elif prev_file:
        vpath = media_store.video_path(project_id, prev_file)
        if vpath.exists():
            out_img = media_store.image_path(project_id, f"shot_{num}_chain_first.jpg")
            await asyncio.to_thread(ds.extract_last_frame, vpath, out_img)
            first_ref = ds.file_to_data_uri(out_img, max_bytes=_VIDEO_IMG_MAX)
    else:
        first_ref = _scene_ref_url(project_id, shot.get("scene_index"))

    # 2) 模型 + media
    user_model = (body.get("model") or "").strip() or VIDEO_MODEL_DEFAULT
    if user_model not in VIDEO_MODEL_CHOICES:
        user_model = VIDEO_MODEL_DEFAULT
    use_scene = bool(body.get("scene_ref", True))
    model = user_model
    media = None
    if first_ref:
        if not user_model.startswith("wan3"):
            model = HAPPYHORSE_I2V_MODEL
        media = ds.first_frame_media(first_ref)
    elif user_model == HAPPYHORSE_R2V_MODEL:
        media_urls, prefix = _build_reference_media(
            project_id, shot, char_map, model, char_limit=8, use_scene=use_scene)
        if media_urls:
            media = ds.ref_media(media_urls)
            prompt = prefix + prompt
        else:
            model = WAN3_VIDEO_MODEL
    elif user_model.startswith("wan3"):
        media_urls, prefix = _build_reference_media(
            project_id, shot, char_map, model, char_limit=9, use_scene=use_scene)
        if media_urls:
            media = ds.ref_media(media_urls[:10])
            prompt = prefix + prompt
    else:
        model = WAN3_VIDEO_MODEL    # happyhorse i2v 必须有首帧，退化为文生视频
    if not prompt and not media:
        raise RuntimeError("该镜头没有视频 Prompt，无法生成")

    # 3) 时长按最终模型夹取 + 字幕
    try:
        dur = int(body.get("duration") or shot.get("duration_seconds", 5) or 5)
    except (TypeError, ValueError):
        dur = 5
    lo, hi = ds.model_duration_range(model)
    if dur != -1:
        dur = max(lo, min(hi, dur))
    sub_cfg = None
    if body.get("subtitle"):
        sc = shot.get("subtitles")
        if isinstance(sc, dict) and sc.get("cues"):
            sub_cfg = sc
        elif dialogue:
            speakers = list(dict.fromkeys(
                (shot.get("characters_present") or []) + list(char_map.keys())))
            sub_cfg = subs.default_subtitles(dialogue, dur, speakers)

    ratio = (body.get("ratio") or "").strip() or None
    if model == HAPPYHORSE_I2V_MODEL:
        ratio = None                  # i2v 比例随首帧
    try:
        seed = int(body.get("seed")) if str(body.get("seed")).strip() not in ("", "None") else None
    except (TypeError, ValueError):
        seed = None
    sub = await ds.submit_video_unified(
        model, prompt, media=media,
        resolution=(body.get("resolution") or "720P").strip(),
        ratio=ratio, duration=dur, audio=bool(body.get("audio")),
        prompt_extend=body.get("prompt_extend"), watermark=False, seed=seed)
    sub["subtitles"] = sub_cfg
    return sub


async def _chain_worker(project_id: str, body: dict, numbers: list):
    """按顺序串行生成：每个镜头完成后抽出尾帧，作为下一个镜头的首帧。"""
    shots = {s["shot_number"]: s for s in media_store.load_storyboard(project_id)}
    char_map = {c.get("name"): c for c in media_store.load_characters(project_id)}
    videos = media_store.load_videos(project_id)
    by_num = {v["shot_number"]: v for v in videos}
    for n in numbers:
        v = by_num.get(n)
        if not v:
            v = {"shot_number": n, "task_id": "", "model": "", "status": "QUEUED",
                 "video_file": "", "error": "", "subtitles": None}
            videos.append(v)
            by_num[n] = v
        v.update(status="QUEUED", error="", chain=True)
    _save_chain_videos(project_id, videos)

    state = {"active": True, "total": len(numbers), "done": 0, "current": 0,
             "error": "", "shots": numbers,
             "started_at": datetime.now().isoformat(timespec="seconds")}
    _save_chain_state(project_id, state)

    prev_file = ""
    try:
        for n in numbers:
            shot = shots.get(n)
            v = by_num[n]
            state["current"] = n
            _save_chain_state(project_id, state)
            if not shot:
                v.update(status="FAILED", error="镜头不存在")
                state["error"] = f"镜头{n}不存在"
                break
            v.update(status="RUNNING", error="")
            _save_chain_videos(project_id, videos)
            try:
                sub = await _submit_chain_shot(project_id, shot, body, char_map, prev_file)
            except Exception as e:
                v.update(status="FAILED", error=str(e)[:200])
                state["error"] = f"镜头{n}：{str(e)[:160]}"
                break
            v.update(status="PENDING", task_id=sub["task_id"],
                     model=sub["model"], subtitles=sub.get("subtitles"),
                     chain=True, error="")
            _save_chain_videos(project_id, videos)
            try:
                out = await _wait_video_task(sub["task_id"])
            except Exception as e:
                v.update(status="FAILED", error=str(e)[:200])
                state["error"] = f"镜头{n}：{str(e)[:160]}"
                break
            try:
                await _finalize_video(project_id, v, out)
            except Exception as e:
                v.update(status="FAILED", error=f"下载/后处理失败：{str(e)[:160]}")
                state["error"] = f"镜头{n}：下载失败 {str(e)[:140]}"
                break
            v["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _save_chain_videos(project_id, videos)
            prev_file = v.get("video_file", "")
            state["done"] = state.get("done", 0) + 1
            _save_chain_state(project_id, state)
    finally:
        state.update(active=False, current=0)
        try:
            _save_chain_state(project_id, state)
        except OSError:
            pass
        try:
            _save_chain_videos(project_id, videos)
        except OSError:
            pass
        _CHAIN_TASKS.pop(project_id, None)


@router.post("/projects/{project_id}/media/videos/chain")
async def chain_videos(project_id: str, body: dict = None):
    """一键启动连续生成：第 1 镜开始 → 完成后抽尾帧 → 作为下一镜首帧，直到结束。"""
    body = body or {}
    running = _CHAIN_TASKS.get(project_id)
    if running and not running.done():
        raise HTTPException(409, "已有一个连续生成任务在运行，请等它结束")
    shots = media_store.load_storyboard(project_id)
    if not shots:
        raise HTTPException(400, "还没有分镜：请先生成分镜 prompt")
    all_nums = [s["shot_number"] for s in shots]
    raw = body.get("shot_numbers") or all_nums
    try:
        nums = sorted({int(x) for x in raw})
    except (TypeError, ValueError):
        raise HTTPException(400, "shot_numbers 必须是镜头号数组")
    valid = set(all_nums)
    nums = [n for n in nums if n in valid]
    if not nums:
        raise HTTPException(400, "没有可生成的镜头")
    task = asyncio.create_task(_chain_worker(project_id, body, nums))
    _CHAIN_TASKS[project_id] = task
    return {"started": True, "total": len(nums), "shots": nums}


@router.get("/projects/{project_id}/media/videos")
async def get_videos(project_id: str):
    """轮询所有未完成任务；成功的下载为本地 mp4。"""
    videos = media_store.load_videos(project_id)
    chain_active = project_id in _CHAIN_TASKS and not _CHAIN_TASKS[project_id].done()
    changed = False
    for v in videos:
        if v.get("chain") and chain_active:
            continue        # 链式任务自己轮询并落盘，避免重复下载
        if v.get("chain") and v.get("status") == "QUEUED":
            # 链已结束但还有排队镜头：任务被中止（失败/服务重启），给出明确反馈
            v.update(status="FAILED",
                     error="连续生成已中断，该镜头未开始；请重新点「一键连续生成」")
            changed = True
            continue
        if v.get("status") in ("PENDING", "RUNNING"):
            try:
                out = await ds.get_task(v["task_id"])
                st = out.get("task_status", "UNKNOWN")
                if st == "SUCCEEDED":
                    await _finalize_video(project_id, v, out)
                    changed = True
                elif st in ("FAILED", "CANCELLED", "UNKNOWN_ERROR"):
                    v.update(status="FAILED",
                             error=out.get("message", "任务失败")[:200])
                    changed = True
                elif st == "RUNNING" and v["status"] != "RUNNING":
                    v["status"] = "RUNNING"
                    changed = True
            except Exception as e:
                v.update(status="FAILED", error=str(e)[:200])
                changed = True
    if changed:
        if chain_active:
            # 链式 worker 在后台持续写盘，合并其最新状态，避免本次保存回滚进度
            latest = {v.get("shot_number"): v
                      for v in media_store.load_videos(project_id)}
            for v in videos:
                if v.get("chain"):
                    cur = latest.get(v.get("shot_number"))
                    if isinstance(cur, dict):
                        v.update(cur)
        media_store.save_videos(project_id, videos)
    return {"videos": videos, "chain": load_chain_state(project_id)}


@router.get("/projects/{project_id}/media/videos/{filename}")
async def serve_video(project_id: str, filename: str):
    p = media_store.video_path(project_id, filename)
    if not p.exists():
        raise HTTPException(404, "视频不存在")
    return FileResponse(p, media_type="video/mp4",
                        filename=filename)


# ── 导出 / 另存到用户指定目录 ────────────────────────────────

def _script_text(db: Session, project_id: str) -> str:
    """优先 Stage5 完整剧本，回退 Stage4 场景拼接（与分镜同源）。"""
    row = db.query(StageCache).filter(
        StageCache.project_id == project_id, StageCache.stage == 5).first()
    if row and row.output_json:
        try:
            s5 = json.loads(row.output_json)
            if isinstance(s5, dict) and s5.get("screenplay_text"):
                return s5["screenplay_text"]
        except (json.JSONDecodeError, TypeError):
            pass
    row = db.query(StageCache).filter(
        StageCache.project_id == project_id, StageCache.stage == 4).first()
    if row and row.output_json:
        try:
            s4 = json.loads(row.output_json)
            if isinstance(s4, list):
                parts = []
                for sc in s4:
                    heading = sc.get("scene_heading", "")
                    body = "\n".join(i.get("text", "") for i in sc.get("content", []))
                    parts.append(f"{heading}\n{body}")
                return "\n\n".join(parts)
        except (json.JSONDecodeError, TypeError):
            pass
    return ""


@router.get("/projects/{project_id}/export-info")
async def export_info(project_id: str):
    """返回默认导出目录，供前端预填保存地址输入框。"""
    return {"default_dir": str(EXPORT_DIR / project_id)}


@router.get("/projects/{project_id}/script-text")
async def get_script_text(project_id: str, db: Session = Depends(get_db)):
    """返回剧本文本（Stage5 回退 Stage4），供前端"选择文件夹导出"写入本地。"""
    return {"text": _script_text(db, project_id)}


@router.post("/projects/{project_id}/export")
async def export_artifacts(project_id: str, body: dict = None,
                           db: Session = Depends(get_db)):
    """把人物图 / 剧本结果 / Prompt 另存到用户指定的本地目录。

    body: {"dir": "目标目录（留空=默认）", "items": ["images","script","prompts"]}
    服务与浏览器同机，dir 为真实本地路径；目录不存在会自动创建。
    """
    body = body or {}
    target = (body.get("dir") or "").strip() or str(EXPORT_DIR / project_id)
    items = body.get("items") or ["images", "script", "prompts"]
    try:
        tdir = Path(target)
        tdir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(400, f"无法创建保存目录 {target}：{e}")

    written, errors = [], []

    if "images" in items:
        idir = tdir / "人物图像"
        idir.mkdir(parents=True, exist_ok=True)
        for c in media_store.load_characters(project_id):
            pre = _safe_name(c.get("name", ""))
            jobs = []
            if c.get("image_file"):
                jobs.append((c["image_file"], f"{pre}_人物图.png"))
            if c.get("turnaround_file"):
                jobs.append((c["turnaround_file"], f"{pre}_三视图.png"))
            for key, e in (c.get("scene_turnarounds") or {}).items():
                if isinstance(e, dict) and e.get("file"):
                    jobs.append((e["file"],
                                 f"{pre}_第{e.get('chapter_index', key)}章场景三视图.png"))
            for src, dst in jobs:
                sp = media_store.image_path(project_id, src)
                if sp.exists():
                    shutil.copy2(sp, idir / dst)
                    written.append(str(idir / dst))
                else:
                    errors.append(f"图片不存在：{src}")

    if "script" in items:
        text = _script_text(db, project_id)
        if text.strip():
            p = tdir / "剧本结果.md"
            p.write_text(text, encoding="utf-8")
            written.append(str(p))
        else:
            errors.append("还没有剧本内容（请先完成流水线 Stage4/5）")

    if "prompts" in items:
        pdir = tdir / "Prompt"
        pdir.mkdir(parents=True, exist_ok=True)
        cp = pdir / "角色提示词.json"
        cp.write_text(json.dumps(
            [{"name": c.get("name"), "role": c.get("role"),
              "visual_description": c.get("visual_description"),
              "image_prompt": c.get("image_prompt")}
             for c in media_store.load_characters(project_id)],
            ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(str(cp))
        shots = media_store.load_storyboard(project_id)
        if shots:
            sp = pdir / "分镜Prompt.json"
            sp.write_text(json.dumps(shots, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            written.append(str(sp))

    if not written and errors:
        raise HTTPException(400, "；".join(errors))
    return {"dir": str(tdir), "files": written, "errors": errors,
            "count": len(written),
            "message": f"已导出 {len(written)} 个文件到 {tdir}"}
