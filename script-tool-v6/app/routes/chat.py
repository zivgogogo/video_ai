"""AI chat endpoint with SSE streaming."""

import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from fastapi import Depends

from app.db import get_db
from app.models import Project, StageCache
from app.ai.factory import create_ai_provider
from app import config as app_config

router = APIRouter(prefix="/api")

BASE_SYSTEM_PROMPT = (
    "You are a professional script writing assistant. "
    "Help users with translation, polishing, summarization, "
    "and script writing questions. Reply in Chinese by default."
)


def _build_project_context(project: Project, db: Session) -> str:
    """Build project context string from cached pipeline stage data."""
    caches = db.query(StageCache).filter(
        StageCache.project_id == project.id
    ).order_by(StageCache.stage).all()

    stage_data = {}
    for c in caches:
        try:
            stage_data[c.stage] = json.loads(c.output_json)
        except (json.JSONDecodeError, TypeError):
            pass

    if not stage_data:
        return ""

    lines = ["\n\n## 当前项目上下文（请基于以下数据回答用户问题）\n"]

    # ── Project info ──
    lines.append(f"### 项目：{project.title}")
    if project.source_novel:
        lines.append(f"- 原著：{project.source_novel}")
    if project.source_author:
        lines.append(f"- 作者：{project.source_author}")
    lines.append(f"- 剧本类型：{project.script_type}")

    # ── Pipeline status overview ──
    lines.append("\n### 流水线完成状态")
    stage_names = ["文本预处理", "分章节分析", "跨章节综合", "剧本结构设计", "逐场内容生成", "组装校验"]
    for i, name in enumerate(stage_names):
        status = "✅ 已完成" if i in stage_data else "⬚ 未运行"
        lines.append(f"- Stage {i}（{name}）：{status}")

    # ── Stage 0: preprocess ──
    if 0 in stage_data:
        d = stage_data[0]
        chapters = d.get("chapters", [])
        lines.append(f"\n### Stage 0 - 文本预处理")
        lines.append(f"- 章节数：{len(chapters)}，总字数：{d.get('total_chars', '?')}")
        if chapters:
            lines.append("- 章节列表：")
            for ch in chapters[:30]:
                title = ch.get("title", f"第{ch.get('index', '?')+1}章")
                lines.append(f"  - {title}（{ch.get('char_count', 0)}字）")

    # ── Stage 1: chapter analyses ──
    if 1 in stage_data:
        d = stage_data[1]
        lines.append(f"\n### Stage 1 - 分章节分析（共 {len(d)} 章已分析）")
        # Collect unique characters
        all_chars = {}
        for ca in d:
            for c in ca.get("new_characters", []):
                name = c.get("name", "")
                if name and name not in all_chars:
                    all_chars[name] = c
        if all_chars:
            lines.append(f"- 发现人物 {len(all_chars)} 个：")
            for name, c in list(all_chars.items())[:25]:
                desc = c.get("description", "")[:60]
                role = c.get("role_hint", "")
                lines.append(f"  - {name}" + (f"（{role}）" if role else "") + (f"：{desc}" if desc else ""))

    # ── Stage 2: global analysis ──
    if 2 in stage_data:
        d = stage_data[2]
        chars = d.get("characters", [])
        rels = d.get("relationships", [])
        lines.append(f"\n### Stage 2 - 跨章节综合")
        lines.append(f"- 综合人物：{len(chars)} 人")
        main_names = [c.get("name", "") for c in chars[:10]]
        lines.append(f"  - 主要人物：{', '.join(main_names)}")
        if rels:
            lines.append(f"- 人物关系（{len(rels)} 条）：")
            for r in rels[:15]:
                lines.append(f"  - {r.get('from', '?')} → {r.get('to', '?')}：{r.get('type', '')}（{r.get('description', '')[:80]}）")
        main_plot = d.get("main_plot", "")
        if main_plot:
            lines.append(f"- 主线情节：{main_plot[:200]}")
        subplots = d.get("subplots", [])
        if subplots:
            lines.append(f"- 支线数量：{len(subplots)} 条")

    # ── Stage 3: structure ──
    if 3 in stage_data:
        d = stage_data[3]
        scenes = d.get("scenes", [])
        lines.append(f"\n### Stage 3 - 剧本结构（共 {len(scenes)} 场）")
        lines.append("- 场景列表：")
        for s in scenes[:40]:
            sid = s.get("id", "?")
            summary = s.get("summary", "")[:80]
            loc = s.get("location", "")
            chars = s.get("characters_present", [])
            lines.append(f"  - {sid}：{summary}" + (f"（地点：{loc}，人物：{', '.join(chars[:5])}）" if loc or chars else ""))
        ep_summaries = d.get("episode_summaries", [])
        if ep_summaries:
            lines.append(f"- 集数规划：{len(ep_summaries)} 集")

    # ── Stage 4: generated scenes ──
    if 4 in stage_data:
        d = stage_data[4]
        lines.append(f"\n### Stage 4 - 已生成场景内容（共 {len(d)} 场）")
        # Show first 5 scene previews
        for s in d[:5]:
            sid = s.get("id", "?")
            heading = s.get("scene_heading", "")
            content = s.get("content", [])
            text_preview = ""
            for item in content[:6]:
                t = item.get("text", "")[:50]
                if t.strip():
                    text_preview += t + " "
            lines.append(f"  - {sid}{' ' + heading if heading else ''}：{text_preview[:150]}...")
        if len(d) > 5:
            lines.append(f"  ...（共 {len(d)} 场，此处仅展示前 5 场预览）")

    # ── Stage 5: assembled script ──
    if 5 in stage_data:
        d = stage_data[5]
        yaml_text = d.get("yaml_text", "")
        screenplay_text = d.get("screenplay_text", "")
        lines.append(f"\n### Stage 5 - 完整剧本已生成")
        lines.append(f"- YAML 剧本：{len(yaml_text)} 字符")
        lines.append(f"- 标准格式剧本：{len(screenplay_text)} 字符")
        if screenplay_text:
            lines.append(f"\n完整标准格式剧本如下（供参考和引用）：\n```\n{screenplay_text[:3000]}\n```")
            if len(screenplay_text) > 3000:
                lines.append(f"\n（剧本总长 {len(screenplay_text)} 字符，以上为前 3000 字符预览。用户可能询问任意部分，请根据场景编号定位。）")

    lines.append("\n请基于以上项目数据回答用户的问题。用户可能会引用场景编号、人物名称等。")
    return "\n".join(lines)

# Provider → (env var name, friendly name for error messages)
PROVIDER_KEY_MAP = {
    "claude":   (app_config.ANTHROPIC_API_KEY, "SCRIPT_TOOL_ANTHROPIC_API_KEY"),
    "openai":   (app_config.OPENAI_API_KEY,    "SCRIPT_TOOL_OPENAI_API_KEY"),
    "deepseek": (app_config.DEEPSEEK_API_KEY,  "SCRIPT_TOOL_DEEPSEEK_API_KEY"),
    "gemini":   (app_config.GEMINI_API_KEY,    "SCRIPT_TOOL_GEMINI_API_KEY"),
    "local":    (True, ""),  # local always considered "configured"
}


@router.post("/projects/{project_id}/chat")
async def chat(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    body = await request.json()
    message = body.get("message", "").strip()
    model_override = body.get("model", "").strip() or None

    if not message:
        raise HTTPException(400, "Message cannot be empty")

    # Resolve provider
    provider_key = model_override or app_config.AI_PROVIDER
    try:
        provider = create_ai_provider(provider=model_override)
    except ValueError:
        return StreamingResponse(
            _error_stream(f"未知模型 '{model_override}'，请选择可用模型"),
            media_type="text/event-stream",
        )

    # Check if API key is configured
    key_info = PROVIDER_KEY_MAP.get(provider_key)
    if key_info and not key_info[0]:
        return StreamingResponse(
            _error_stream(f"未配置 {key_info[1]}，请在 .env 文件中设置该环境变量后重启"),
            media_type="text/event-stream",
        )

    context = _build_project_context(project, db)
    system_prompt = BASE_SYSTEM_PROMPT + context

    async def event_stream():
        full_text = ""
        try:
            async for chunk in provider.generate_stream(message, system=system_prompt):
                full_text += chunk
                yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            if not full_text:
                err_msg = str(e)
                # 友好的常见错误翻译
                if "401" in err_msg or "Unauthorized" in err_msg or "Incorrect API key" in err_msg:
                    err_msg = f"API Key 无效或未配置，请检查 {key_info[1] if key_info else '对应环境变量'}"
                yield f"data: {json.dumps({'error': err_msg}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _error_stream(message: str):
    """Generate a single-error SSE stream."""
    async def gen():
        yield f"data: {json.dumps({'error': message}, ensure_ascii=False)}\n\n"
    return gen()
