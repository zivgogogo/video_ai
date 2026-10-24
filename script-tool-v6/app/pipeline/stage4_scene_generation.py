import asyncio
from dataclasses import dataclass, field
from app.ai.interface import AIProvider
from app.ai.factory import create_ai_provider, generate_with_pool_fallback
from app.pipeline.stage3_script_structure import ScenePlan
from app.pipeline.utils import extract_json

# 并发上限：避免同时发起过多请求触发 API 限流
MAX_CONCURRENCY = 5

@dataclass
class GeneratedScene:
    id: str = ""
    act: int = 1
    episode: int = 1
    sequence: int = 1
    location: str = ""
    time: str = ""
    setting_description: str = ""
    scene_heading: str = ""
    characters_present: list = field(default_factory=list)
    content: list = field(default_factory=list)
    raw_response: str = ""

SYSTEM_PROMPT = """你是一位专业的电视剧编剧。根据场景计划和人物信息，生成该场景的完整剧本内容。按照中国电视剧标准剧本格式输出 JSON。

输出格式：
{
  "scene_heading": "[外景/内景：地点描述，时间]",
  "content": [
    {"type": "action", "text": "镜头/动作/环境描述"},
    {"type": "dialogue", "character": "角色名", "text": "台词", "direction": "表情/语气提示（可选）"},
    {"type": "narration", "text": "旁白内容", "direction": "声音描述（可选）"},
    {"type": "inner_monologue", "character": "角色名", "text": "内心独白内容"},
    {"type": "transition", "text": "转场描述"}
  ]
}

内容类型说明：
- action：用【】包裹，描述镜头运动、环境氛围、角色动作和表情。角色首次出场时标注全名、性别、年龄、身份。
- dialogue：角色对白，格式为「角色名： （表情提示）台词」。direction 指括号里的表情/动作/语气提示。
- narration：旁白/画外音，用于故事背景介绍或情感升华。direction 描述声音质感（如"温暖深沉的男声"）。
- inner_monologue：角色内心独白，表达角色未说出口的想法。
- transition：场景切换，如 CUT TO: 或 [转换场景：...]。

剧本格式规则：
1. scene_heading 使用 [内景/外景：地点，时间] 格式
2. action 内容丰富具体，包含镜头语言和视觉细节
3. dialogue 台词贴合角色性格和身份，语气自然
4. 对话中穿插动作和反应，避免连续过长对白
5. 每场控制在 5-15 个 content 元素
6. 如有原始小说对话参考，从中把握角色的说话风格"""


async def generate_scene(plan: ScenePlan, characters: list,
                         original_text: str = "",
                         dialogue_excerpts: list = None,
                         provider: AIProvider = None) -> GeneratedScene:
    if provider is None:
        provider = create_ai_provider()

    scene_chars = [c for c in characters if c["name"] in plan.characters_present]
    char_desc = "\n".join(
        f"- {c['name']}（{c.get('role','')}）：{c.get('description','')}，性格：{', '.join(c.get('traits',[]))}"
        for c in scene_chars
    )

    # 构建原始对话参考（最多 5 条）
    dialogue_ref = ""
    if dialogue_excerpts:
        excerpts_lines = []
        for ex in dialogue_excerpts[:5]:
            speaker = ex.get("speaker", "?")
            text = ex.get("text", "")
            context = ex.get("context", "")
            line = f"- {speaker}：「{text}」"
            if context:
                line += f"（{context}）"
            excerpts_lines.append(line)
        if excerpts_lines:
            dialogue_ref = (
                "\n原始小说对话参考（参考角色语气和说话风格）：\n"
                + "\n".join(excerpts_lines)
                + "\n"
            )

    prompt = f"""请为以下场景生成标准中国电视剧剧本内容：

场景编号：{plan.id}
地点：{plan.location}
时间：{plan.time}
环境描述：{plan.setting_description}
出场人物：{', '.join(plan.characters_present)}
场景概要：{plan.summary}

人物详细信息：
{char_desc}

原始小说参考片段：
{original_text[:2000]}
{dialogue_ref}
请生成该场景的完整剧本内容。要求：
1. scene_heading 格式为 [内景/外景：地点，时间]
2. 动作描述使用镜头语言，内容具体生动
3. 对白贴合角色性格，语气自然口语化
4. 合适的时机使用旁白或内心独白增强情感
5. 每场 5-15 个内容元素"""

    response = await generate_with_pool_fallback(provider, prompt, system=SYSTEM_PROMPT, output_format="json")
    return _parse_scene(plan, response)


async def generate_scenes_parallel(plans: list, characters: list,
                                   chapter_texts: dict,
                                   chapter_analyses: list = None,
                                   provider: AIProvider = None,
                                   on_scene_done=None) -> list:
    if provider is None:
        provider = create_ai_provider()

    # 构建章节索引 → 对话摘录的映射
    chapter_dialogue_map = {}
    if chapter_analyses:
        for ca in chapter_analyses:
            if ca.dialogue_excerpts:
                chapter_dialogue_map[ca.chapter_index] = ca.dialogue_excerpts

    async def _gen_one(plan: ScenePlan) -> GeneratedScene:
        async with sem:
            return await generate_scene(
                plan, characters,
                chapter_texts.get(plan.source_chapter, ""),
                chapter_dialogue_map.get(plan.source_chapter, []),
                provider,
            )

    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    # 第一轮并行生成
    tasks = [_gen_one(p) for p in plans]
    results = []
    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        if on_scene_done:
            await on_scene_done()

    # 重试空场景（最多 2 次）
    MAX_RETRIES = 2
    for attempt in range(MAX_RETRIES):
        empty = [r for r in results if not r.content]
        if not empty:
            break
        print(f"[generate_scenes_parallel] 第 {attempt+1} 次重试 {len(empty)} 个空场景："
              f"{', '.join(s.id for s in empty)}")
        retry_tasks = [_gen_one(s) for s in empty]
        retry_results = []
        for coro in asyncio.as_completed(retry_tasks):
            new_result = await coro
            retry_results.append(new_result)
            if on_scene_done:
                await on_scene_done()
        # 替换原结果
        retry_map = {r.id: r for r in retry_results}
        for i, r in enumerate(results):
            if not r.content and r.id in retry_map:
                results[i] = retry_map[r.id]

    # 按原始分镜计划顺序排序（sequence 为幕内编号，不能全局排序）
    order = {p.id: i for i, p in enumerate(plans)}
    results.sort(key=lambda r: order.get(r.id, len(order)))
    return results


def _parse_scene(plan: ScenePlan, response: str) -> GeneratedScene:
    scene = GeneratedScene(
        id=plan.id, act=plan.act, episode=plan.episode,
        sequence=plan.sequence, location=plan.location,
        time=plan.time, setting_description=plan.setting_description,
        characters_present=plan.characters_present,
        raw_response=response,
    )
    data = extract_json(response)
    if data:
        scene.scene_heading = data.get("scene_heading", "")
        scene.content = data.get("content", [])

    # 校验：content 为空时输出诊断信息
    if not scene.content:
        if not response or not response.strip():
            print(f"[_parse_scene] WARNING: {plan.id} AI 返回了空响应")
        elif not data:
            print(f"[_parse_scene] WARNING: {plan.id} JSON 解析失败，content 为空")
            print(f"[_parse_scene] raw_response 前 500 字符：\n{response[:500]}")
        else:
            print(f"[_parse_scene] WARNING: {plan.id} JSON 解析成功但 content 数组为空")
            print(f"[_parse_scene] 解析出的 key: {list(data.keys())}")
            print(f"[_parse_scene] raw_response 前 500 字符：\n{response[:500]}")

    return scene
