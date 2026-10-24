"""剧本 → 分镜 prompt JSON（供文生图/视频生成使用）。

v4 改进：
- 按场景逐场生成：覆盖整本长篇，不再受"整本一次性 6-12 镜头 + 9000 字截断"限制；
- 结构化 prompt 模板：主体(角色外观锚定)/动作/环境/光线/镜头(焦段·运动·速度)/风格/画质；
- 统一风格锚 + 负面约束（无文字/水印/畸形），保证跨镜头一致；
- 台词/内心独白/旁白从 Stage4 结构化内容显式喂给分镜模型，便于后续字幕与表演。
"""
import asyncio
import json
import re

from sqlalchemy.orm import Session

from app.models import StageCache
from app.ai.factory import create_ai_provider, generate_with_pool_fallback
from app.media import media_store
from app.media import prompt_elements as pe
from app.pipeline.utils import extract_json

STORYBOARD_SYSTEM = "你是资深分镜师与摄影指导。只输出合法 JSON，不要其他文字。"

# 逐场生成的并发上限（与流水线 Stage4 保持一致的量级，避免触发 API 限流）
MAX_CONCURRENCY = 3

# 统一风格锚：所有镜头共用，保证跨镜头画风一致
STYLE_ANCHOR = ("电影感写实风格，35mm 胶片质感，自然光与实用光源为主，明暗层次分明，"
                "真实皮肤与布料质感，浅景深，构图讲究，画面干净通透。")

# 负面约束统一放在 prompt_elements.NEGATIVE_RULES，汇总时自动追加


def _options_menu() -> str:
    """把专业要素候选渲染成菜单文本，注入提示词供 AI 从中挑选。"""
    lines = []
    for k, v in pe.ELEMENT_OPTIONS.items():
        lines.append(f"- {k}（{v['label']}）：{' / '.join(v['options'])}")
    return "\n".join(lines)


STORYBOARD_PROMPT = """把下面这一场戏拆成 {shots} 个用于 AI 视频生成的分镜镜头，严格覆盖本场关键剧情与台词，不遗漏重要动作。

【场景信息】
标题：{scene_title}
场景头：{scene_heading}
地点 / 时间：{location} / {time}
环境：{setting}
出场角色：{characters}

【角色外观设定】（写 subject 时必须用它锚定角色外观，禁止用“一名男子/年轻女子/反派”等模糊指代）
{appearances}

【本场剧本内容】（含动作/对白/内心独白/旁白）
{scene_text}

【统一风格锚】（整体基调参考）
{style}

【专业要素候选】（每个镜头的 elements 从下列选项中挑选最贴合的；也可填更贴切的自定义值；不确定就留空字符串或空数组）
{options_menu}

每个镜头输出以下字段：
- shot_number：本场内从 1 递增（最终会全局重排）
- scene_title：固定填 "{scene_title}"
- characters_present：出场角色名列表（用【角色外观设定】里的准确名字）
- duration_seconds：从 5 / 10 / 15 中选（动作越复杂、台词越长给越长；普通叙述给 5）
- elements：对象，键包括——
  文本类：subject（主体/人物，含外观锚定）、action（动作/表演，具体可视化）、dialogue（本镜台词或内心独白，无则空字符串；内心独白加〔内心〕前缀，旁白加〔旁白〕前缀）、scene（场景/空间）、environment（环境细节：背景/前景/天气/陈设）
  选项类（从上面候选中选最贴切的）：shot_type、shot_size、camera_angle、focal_length、camera_movement、composition、time_of_day、light_source、lighting（数组，可多选）、color_tone、contrast、mood、emotion、visual_style、quality（数组，可多选）

只输出 JSON：{{"shots":[{{"shot_number":1,"scene_title":"...","characters_present":["..."],"duration_seconds":5,"elements":{{"subject":"...","shot_size":"..."}}}}]}}"""


def _stage_data(db: Session, project_id: str, stage: int):
    row = db.query(StageCache).filter(
        StageCache.project_id == project_id,
        StageCache.stage == stage).first()
    if row and row.output_json:
        try:
            return json.loads(row.output_json)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _render_scene_content(content) -> str:
    """把 Stage4 场景的 content 列表渲染成可读文本（区分对白/独白/旁白/动作）。"""
    lines = []
    for it in content or []:
        if not isinstance(it, dict):
            continue
        t = it.get("type", "")
        txt = (it.get("text") or "").strip()
        who = (it.get("character") or "").strip()
        direction = (it.get("direction") or "").strip()
        if t == "dialogue":
            if not txt:
                continue
            lines.append(f"{who}（{direction}）：「{txt}」" if direction
                         else f"{who}：「{txt}」")
        elif t == "inner_monologue":
            if txt:
                lines.append(f"{who}〔内心独白〕：{txt}")
        elif t == "narration":
            if txt:
                lines.append(f"〔旁白〕{txt}")
        elif t == "transition":
            if txt:
                lines.append(f"〔转场〕{txt}")
        else:  # action 或未知类型
            if txt:
                lines.append(f"【动作/环境】{txt}")
    return "\n".join(lines)


def _scene_list(db: Session, project_id: str) -> list:
    """优先用 Stage4 结构化场景；回退到把 Stage5 剧本文本按场景头切分。"""
    scenes = []
    s4 = _stage_data(db, project_id, 4)
    if isinstance(s4, list):
        for sc in s4:
            if not isinstance(sc, dict):
                continue
            text = _render_scene_content(sc.get("content"))
            if not text.strip():
                continue
            scenes.append({
                "title": sc.get("scene_heading") or sc.get("location") or f"场景{len(scenes) + 1}",
                "scene_heading": sc.get("scene_heading", ""),
                "location": sc.get("location", ""),
                "time": sc.get("time", ""),
                "setting": sc.get("setting_description", ""),
                "characters": sc.get("characters_present", []) or [],
                "text": text,
            })
    if scenes:
        return scenes

    # 回退：Stage5 完整剧本文本，按场景头 [内景/外景：...] 切分
    s5 = _stage_data(db, project_id, 5)
    text5 = s5.get("screenplay_text", "") if isinstance(s5, dict) else ""
    if text5.strip():
        for ch in re.split(r"\n(?=\s*\[(?:内景|外景|内|外))", text5):
            ch = ch.strip()
            if not ch:
                continue
            head = ch.splitlines()[0][:40]
            scenes.append({"title": head or f"场景{len(scenes) + 1}",
                           "scene_heading": head, "location": "", "time": "",
                           "setting": "", "characters": [], "text": ch})
    return scenes


def _appearances(db: Session, project_id: str) -> str:
    """角色外观锚定：优先角色档案(characters.json)，回退 Stage2 综合人物档案。"""
    lines = []
    for c in media_store.load_characters(project_id):
        name = (c.get("name") or "").strip()
        if not name:
            continue
        app = (c.get("visual_description") or c.get("image_prompt") or "").strip()
        if app:
            lines.append(f"- {name}：{app[:160]}")
    if not lines:
        s2 = _stage_data(db, project_id, 2)
        if isinstance(s2, dict):
            for c in s2.get("characters", []) or []:
                if not isinstance(c, dict):
                    continue
                name = (c.get("name") or "").strip()
                app = (c.get("appearance") or c.get("visual_description")
                       or c.get("description") or "").strip()
                if name and app:
                    lines.append(f"- {name}：{app[:160]}")
    return "\n".join(lines) or ("（暂无角色外观设定，请依据剧本推断，"
                                "并在所有镜头中保持同一角色外观一致）")


def _normalize_shot(raw: dict, scene_index: int, scene_title: str) -> dict:
    """把 AI 返回的结构化镜头规整成标准 shot：补全 elements、汇总 prompt、回填顶层兼容字段。"""
    els = pe.new_elements()
    got = raw.get("elements") or {}
    for k in els:
        v = got.get(k)
        if v not in (None, "", []):
            els[k] = v
    # 文本类也可能被 AI 放在顶层
    for k in ("subject", "action", "dialogue", "scene", "environment"):
        if not els.get(k) and raw.get(k):
            els[k] = raw[k]
    # 风格/画质兜底，保证电影感基调
    if not els.get("visual_style"):
        els["visual_style"] = "电影感写实"
    if not els.get("quality"):
        els["quality"] = ["电影级", "高清"]

    try:
        dur = int(raw.get("duration_seconds") or 5)
    except (TypeError, ValueError):
        dur = 5
    # 对齐 happyhorse 单条上限（3–15s）；选 wan3.0 时提交阶段可再放宽到 30s
    dur = max(3, min(15, dur))
    cam = " ".join(x for x in [els.get("camera_angle", ""),
                               els.get("camera_movement", "")] if x)
    return {
        "shot_number": raw.get("shot_number"),   # 稍后全局重排
        "scene_title": raw.get("scene_title") or scene_title,
        "scene_index": scene_index,
        "characters_present": raw.get("characters_present") or [],
        "duration_seconds": dur,
        "elements": els,
        # 顶层冗余字段（向后兼容分镜表/字幕/导出）
        "shot_size": els.get("shot_size", ""),
        "camera_angle": cam,
        "frame_description": " ".join(x for x in [els.get("scene", ""),
                                                  els.get("environment", "")] if x),
        "character_action": els.get("action", ""),
        "dialogue": els.get("dialogue", ""),
        "video_prompt": pe.assemble_video_prompt(els),
        "ai_image_prompt": pe.assemble_image_prompt(els),
    }


async def generate_storyboard(db: Session, project_id: str,
                              shots_per_scene=4, max_scenes=None,
                              protect_confirmed=True) -> list:
    """按场景逐场生成分镜，合并后全局重排 shot_number。

    shots_per_scene：每场目标镜头数（1-10）；max_scenes：最多处理多少场（默认全部）。
    逐场并发生成（受 MAX_CONCURRENCY 限流），单场失败不影响其余场。
    """
    scenes = _scene_list(db, project_id)
    if not scenes:
        raise ValueError("还没有剧本内容：请先完成流水线生成（Stage 4/5）")
    if max_scenes:
        try:
            scenes = scenes[:max(1, int(max_scenes))]
        except (TypeError, ValueError):
            pass
    try:
        shots_per_scene = max(1, min(int(shots_per_scene or 4), 10))
    except (TypeError, ValueError):
        shots_per_scene = 4

    # v6：保护 Prompt 中心已确认(✅)的镜头——其所属场景整体跳过重生成，内容原样保留；
    # 以 Prompt 中心保存的为准，重新生成只补未确认/新增的场景。
    kept, skip_scenes = [], set()
    if protect_confirmed:
        for s in media_store.load_storyboard(project_id):
            if s.get("confirmed"):
                kept.append(s)
                si = s.get("scene_index")
                if isinstance(si, int):
                    skip_scenes.add(si)

    appearances = _appearances(db, project_id)
    provider = create_ai_provider()
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def _gen_scene(idx: int, sc: dict) -> list:
        prompt = STORYBOARD_PROMPT.format(
            shots=shots_per_scene, scene_title=sc["title"],
            scene_heading=sc["scene_heading"] or "（无）",
            location=sc["location"] or "（未指定）", time=sc["time"] or "（未指定）",
            setting=sc["setting"] or "（见剧本内容）",
            characters="、".join(sc["characters"]) or "（未指定）",
            appearances=appearances, scene_text=sc["text"][:4000],
            style=STYLE_ANCHOR, options_menu=_options_menu())
        async with sem:
            try:
                text = await generate_with_pool_fallback(
                    provider, prompt, system=STORYBOARD_SYSTEM, output_format="json")
            except Exception:
                return []   # 单场失败（限流/超时）不阻断其余场
        data = extract_json(text) or {}
        out = []
        for s in data.get("shots", []):
            if not isinstance(s, dict):
                continue
            if isinstance(s.get("elements"), dict) and s["elements"]:
                out.append(_normalize_shot(s, idx, sc["title"]))
            elif s.get("video_prompt"):
                # 兼容：AI 仍按旧格式只给了段落式 video_prompt
                s.setdefault("scene_title", sc["title"])
                s["scene_index"] = idx
                out.append(s)
        return out

    # 只重新生成「没有已确认镜头」的场景；已确认的场景整体跳过
    gen_idx = [i for i in range(len(scenes)) if i not in skip_scenes]
    results = await asyncio.gather(*[_gen_scene(i, scenes[i]) for i in gen_idx]) if gen_idx else []
    new_shots = []
    for r in results:
        new_shots.extend(r)

    merged = kept + new_shots
    if not merged:
        raise ValueError("AI 未返回有效分镜（可能剧本为空或模型限流，请重试）")
    # 按场景顺序稳定排序后全局重排 shot_number（已确认镜头内容/状态原样保留）
    merged.sort(key=lambda s: s.get("scene_index")
                if isinstance(s.get("scene_index"), int) else 10 ** 6)
    for i, s in enumerate(merged, 1):
        s["shot_number"] = i

    media_store.save_storyboard(project_id, merged)
    return merged


async def refine_split_parts(scene_title: str, base_elements: dict,
                             characters: list, parts_dialogue: list) -> list:
    """拆分镜头时，用 AI 为每段（台词已分配好）重配贴合的画面要素。

    一次调用返回 N 段 elements：保持人物/场景/环境/画风一致，只按各段台词
    重新设计动作、景别、机位、运镜、情绪等。返回 [dict|None]*N（None=沿用原要素）。
    """
    n = len(parts_dialogue)
    if n == 0:
        return []
    be = base_elements or {}
    seg_lines = "\n".join(f"段{i + 1}台词：{d}" for i, d in enumerate(parts_dialogue))
    prompt = f"""你是专业影视分镜师。一个镜头对白过长，已按句拆成 {n} 段（每段台词已固定，见下）。
请为每一段重新设计【画面要素】，让画面与各自台词匹配；人物、场景、环境、画风必须与原镜头保持一致，只调整动作、景别、机位角度、焦段、运镜、构图、情绪等。

【原镜头上下文】
- 场次标题：{scene_title or '未命名'}
- 场景/环境：{be.get('scene', '')} / {be.get('environment', '')}
- 出场角色：{'、'.join(characters) if characters else '（无）'}
- 原画面主体：{be.get('subject', '')}
- 原角色动作：{be.get('action', '')}
- 原镜头选项：景别 {be.get('shot_size', '')}｜机位 {be.get('camera_angle', '')}｜运镜 {be.get('camera_movement', '')}｜情绪 {be.get('emotion', '')}

【各段台词（固定，勿改）】
{seg_lines}

【要素候选（选项类字段尽量从中选）】
{_options_menu()}

请只输出 JSON：{{"parts": [{{"elements": {{...}}}}, ...]}}，共 {n} 个，顺序与段落一致。
每个 elements 必含：subject、action、dialogue（=该段台词原文）、scene、environment、shot_type、shot_size、camera_angle、focal_length、camera_movement、composition、time_of_day、light_source、lighting(数组)、color_tone、contrast、mood、emotion、visual_style、quality(数组)。
其中 scene/environment/visual_style/subject 与原镜头一致；action/shot_size/camera_movement/mood/emotion 按该段台词重新设计。不要输出多余文字。"""
    try:
        provider = create_ai_provider("default")
        raw = await generate_with_pool_fallback(
            provider, [{"role": "user", "content": prompt}], temperature=0.5)
        data = extract_json(raw)
        parts = data.get("parts") if isinstance(data, dict) else None
        if not isinstance(parts, list):
            return [None] * n
        out = []
        for i in range(n):
            p = parts[i] if i < len(parts) else None
            el = p.get("elements") if isinstance(p, dict) else None
            if not isinstance(el, dict):
                out.append(None)
                continue
            merged = dict(be)
            merged.update({k: v for k, v in el.items() if v not in (None, "", [])})
            merged["dialogue"] = parts_dialogue[i]        # 台词以分配结果为准
            out.append(merged)
        return out
    except Exception:
        return [None] * n


# ── v6：AI 自动分时（把镜头按时长拆成时间轴 beats）──────────────
AUTO_BEATS_SYSTEM = "你是资深分镜师与剪辑。只输出合法 JSON，不要其他文字。"

AUTO_BEATS_PROMPT = """把这个镜头按时长拆成 2-4 个连续的时间分段（beats），用于「时间戳定向」的视频 prompt。

【镜头时长】{duration} 秒
【主体/人物】{subject}
【场景/环境】{scene} / {environment}
【角色动作】{action}
【台词】{dialogue}
【现有汇总 Prompt】{video_prompt}

要求：
- 每段给 start/end（秒）：从 0 到 {duration} 连续覆盖、不重叠、不留空；
- action：该段的画面/动作，具体可视化，和台词节奏对应；
- camera：该段的运镜或景别变化；
- dialogue：该段对应的台词片段（把总台词按时间合理分配；无台词则空字符串）。

只输出 JSON：{{"beats":[{{"start":0,"end":3,"action":"","camera":"","dialogue":""}}]}}"""


async def gen_beats_for_shot(shot: dict, duration=None) -> list:
    """v6：用 AI 把一个镜头按时长自动拆成时间轴分段（beats），供时间戳定向 prompt。

    依据镜头的主体/场景/动作/台词，生成 2-4 段连续时间轴（每段
    start/end/action/camera/dialogue），返回规整后的 beats（用户可再手动微调）。
    """
    els = shot.get("elements") or {}
    try:
        dur = int(duration or shot.get("duration_seconds") or 5)
    except (TypeError, ValueError):
        dur = 5
    dur = max(2, min(dur, 30))
    prompt = AUTO_BEATS_PROMPT.format(
        duration=dur,
        subject=els.get("subject", "") or shot.get("frame_description", ""),
        scene=els.get("scene", ""), environment=els.get("environment", ""),
        action=els.get("action", "") or shot.get("character_action", ""),
        dialogue=els.get("dialogue", "") or shot.get("dialogue", ""),
        video_prompt=(shot.get("video_prompt", "") or "")[:500])
    provider = create_ai_provider()
    text = await generate_with_pool_fallback(
        provider, prompt, system=AUTO_BEATS_SYSTEM, output_format="json")
    data = extract_json(text) or {}
    beats = data.get("beats") if isinstance(data, dict) else None
    return pe.normalize_beats(beats or [], dur)
