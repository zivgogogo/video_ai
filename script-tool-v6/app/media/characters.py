"""v3：角色视觉档案提取（流水线分析数据 → LLM 视觉设定）。"""
import json

from sqlalchemy.orm import Session

from app.models import StageCache
from app.ai.factory import create_ai_provider, generate_with_pool_fallback
from app.media import media_store
from app.pipeline.utils import extract_json

CHARACTER_VISUAL_SYSTEM = ("你是影视制作选角与视觉设计总监。只输出合法 JSON，不要其他文字。")

CHARACTER_VISUAL_PROMPT = """根据以下小说分析中的角色信息，为主要角色（最多6个，按重要性排序）生成"视觉档案"，用于 AI 文生角色图与视频角色一致性。

要求：
- visual_description：外貌设定（年龄/性别/脸型/眼睛/发型/体型/气质），80-120字
- image_prompt：中文文生图提示词，100-150字，包含服装、发型、五官、气质与"电影感写实风格，柔和光"等风格词，同一角色措辞必须稳定一致
- 年龄必须写实锁定：写明具体年龄段（如"18-20岁少女"/"40岁中年男性"）。年轻角色务必加幼态词（稚气未脱、圆润饱满的少女脸颊、胶原蛋白感、学生气、皮肤细腻无皱纹）并加"不要成熟、不要显老"，防止写实模型把脸拍大；年长角色写明年龄，避免拍小

角色信息：
{chars}

输出 JSON 格式：
{{"characters":[{{"name":"","role":"","visual_description":"","image_prompt":""}}]}}"""


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


def _gather_raw_characters(db: Session, project_id: str) -> list:
    """优先取 Stage2 综合人物，缺失时回退 Stage1 各章人物合并。"""
    s2 = _stage_data(db, project_id, 2)
    if s2 and s2.get("characters"):
        return s2["characters"]
    s1 = _stage_data(db, project_id, 1)
    merged = {}
    if s1:
        for ca in s1:
            for c in ca.get("new_characters", []):
                name = c.get("name", "")
                if name and name not in merged:
                    merged[name] = c
    return list(merged.values())


async def extract_character_profiles(db: Session, project_id: str) -> list:
    raw = _gather_raw_characters(db, project_id)
    if not raw:
        raise ValueError("还没有角色数据：请先完成流水线 Stage 1/2（章节分析）")

    existing = {c.get("name"): c for c in media_store.load_characters(project_id)}

    provider = create_ai_provider()
    prompt = CHARACTER_VISUAL_PROMPT.format(
        chars=json.dumps(raw, ensure_ascii=False)[:6000])
    text = await generate_with_pool_fallback(
        provider, prompt, system=CHARACTER_VISUAL_SYSTEM, output_format="json")

    data = extract_json(text) or {}
    profiles = []
    for item in data.get("characters", []):
        name = (item.get("name") or "").strip()
        if not name:
            continue
        old = existing.get(name, {})
        profiles.append({
            "name": name,
            "role": item.get("role", old.get("role", "")),
            "visual_description": item.get("visual_description", ""),
            "image_prompt": item.get("image_prompt", ""),
            # 保留已生成的图像信息
            "image_url": old.get("image_url", ""),
            "image_file": old.get("image_file", ""),
        })
    if not profiles:
        raise ValueError("AI 未返回有效角色档案")

    media_store.save_characters(project_id, profiles)
    return profiles
