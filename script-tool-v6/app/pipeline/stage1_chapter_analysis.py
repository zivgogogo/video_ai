import json
import asyncio
from dataclasses import dataclass, field
from app.ai.interface import AIProvider
from app.ai.factory import create_ai_provider, generate_with_pool_fallback
from app.pipeline.stage0_preprocess import Chapter
from app.pipeline.utils import extract_json

# 并发上限：避免同时发起过多请求触发 API 限流
MAX_CONCURRENCY = 5

@dataclass
class ChapterAnalysis:
    chapter_index: int
    chapter_title: str
    new_characters: list = field(default_factory=list)
    locations: list = field(default_factory=list)
    plot_events: list = field(default_factory=list)
    dialogue_excerpts: list = field(default_factory=list)
    raw_response: str = ""

SYSTEM_PROMPT = """你是一位专业的剧本分析师。分析给定的小说章节，输出 JSON。只输出 JSON，不要其他文字。

输出格式：
{
  "new_characters": [
    {"name": "角色名", "aliases": ["别名"], "description": "简要描述", "traits": ["性格标签"], "role_hint": "protagonist/antagonist/supporting/cameo"}
  ],
  "locations": [
    {"name": "地点名", "description": "简要描述", "time_hint": "时间提示"}
  ],
  "plot_events": [
    {"summary": "事件摘要", "importance": "major/minor", "characters_involved": ["角色名"]}
  ],
  "dialogue_excerpts": [
    {"speaker": "说话者", "text": "台词片段", "context": "上下文"}
  ]
}"""


async def analyze_chapter(chapter: Chapter, provider: AIProvider = None) -> ChapterAnalysis:
    if provider is None:
        provider = create_ai_provider()

    prompt = f"""分析以下小说章节：

章节标题：{chapter.title}
章节内容：
{chapter.content[:6000]}

请输出该章节的人物、地点、情节事件和对话片段。"""

    response = await generate_with_pool_fallback(provider, prompt, system=SYSTEM_PROMPT, output_format="json")
    return _parse_response(chapter.index, chapter.title, response)


async def analyze_chapters_parallel(chapters: list, provider: AIProvider = None,
                                   on_chapter_done=None) -> list:
    if provider is None:
        provider = create_ai_provider()

    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def _one(c: Chapter) -> ChapterAnalysis:
        async with sem:
            return await analyze_chapter(c, provider)

    tasks = [_one(c) for c in chapters]

    # 使用 as_completed 实现逐章进度回调
    results = []
    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        if on_chapter_done:
            await on_chapter_done()

    # 按章节索引排序，确保顺序一致
    results.sort(key=lambda r: r.chapter_index)
    return results


def _parse_response(index: int, title: str, response: str) -> ChapterAnalysis:
    analysis = ChapterAnalysis(chapter_index=index, chapter_title=title, raw_response=response)
    data = extract_json(response)
    if data:
        analysis.new_characters = data.get("new_characters", [])
        analysis.locations = data.get("locations", [])
        analysis.plot_events = data.get("plot_events", [])
        analysis.dialogue_excerpts = data.get("dialogue_excerpts", [])
    return analysis
