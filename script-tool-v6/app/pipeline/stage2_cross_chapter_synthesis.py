import json
from dataclasses import dataclass, field
from app.ai.interface import AIProvider
from app.ai.factory import create_ai_provider
from app.pipeline.stage1_chapter_analysis import ChapterAnalysis
from app.pipeline.utils import extract_json

@dataclass
class GlobalAnalysis:
    characters: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    locations: list = field(default_factory=list)
    main_plot: str = ""
    subplots: list = field(default_factory=list)
    raw_response: str = ""

SYSTEM_PROMPT = """你是一位专业的剧本分析师。根据各章节的人物、地点和情节分析，综合整理出完整的人物表、关系图、场景目录和情节线。输出 JSON。

输出格式：
{
  "characters": [
    {"name": "", "aliases": [], "role": "protagonist/antagonist/supporting/cameo", "description": "", "traits": [], "first_appearance_chapter": 1}
  ],
  "relationships": [
    {"from": "角色A", "to": "角色B", "type": "师徒/父子/恋人/仇敌/朋友", "description": ""}
  ],
  "locations": [
    {"name": "", "description": "", "chapters": [1, 2]}
  ],
  "main_plot": "主线情节一句话概述",
  "subplots": ["支线1概述", "支线2概述"]
}"""


async def synthesize(chapter_analyses: list, provider: AIProvider = None) -> GlobalAnalysis:
    if provider is None:
        provider = create_ai_provider()

    summary_parts = []
    for ca in chapter_analyses:
        summary_parts.append(f"""
第{ca.chapter_index+1}章：{ca.chapter_title}
人物：{json.dumps(ca.new_characters, ensure_ascii=False)}
地点：{json.dumps(ca.locations, ensure_ascii=False)}
情节：{json.dumps(ca.plot_events, ensure_ascii=False)}
对话：{json.dumps(ca.dialogue_excerpts, ensure_ascii=False)}
""")

    prompt = f"""综合以下各章节分析结果，生成完整的人物表、关系图、场景目录和情节概述：

{''.join(summary_parts[:8000])}

请输出完整的综合分析。"""

    response = await provider.generate(prompt, system=SYSTEM_PROMPT, output_format="json")
    return _parse_global(response)


def _parse_global(response: str) -> GlobalAnalysis:
    result = GlobalAnalysis(raw_response=response)
    data = extract_json(response)
    if data:
        result.characters = data.get("characters", [])
        result.relationships = data.get("relationships", [])
        result.locations = data.get("locations", [])
        result.main_plot = data.get("main_plot", "")
        result.subplots = data.get("subplots", [])
    return result
