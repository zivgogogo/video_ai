# AI 辅助剧本创作工具 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Web 应用，将 3 章以上小说文本自动转换为结构化 YAML 剧本。

**Architecture:** FastAPI + Jinja2 SSR + SQLite 的单体应用。核心是一个 6 阶段 AI 流水线（预处理 → 分章节分析 → 跨章节综合 → 剧本结构设计 → 逐场内容生成 → 组装校验），通过抽象 AI Provider 接口支持 Claude/GPT/本地模型切换。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Jinja2, HTMX, SQLite, anthropic SDK, openai SDK

---

### Task 1: 项目脚手架

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/main.py`

- [ ] **Step 1: 创建 requirements.txt**

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.35
jinja2==3.1.4
python-multipart==0.0.12
anthropic==0.40.0
openai==1.55.0
python-docx==1.1.2
markdown==3.7
pyyaml==6.0.2
pytest==8.3.0
httpx==0.28.0
```

- [ ] **Step 2: 创建 app/config.py**

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
CACHE_DIR = STORAGE_DIR / "cache"
DATABASE_URL = f"sqlite:///{STORAGE_DIR / 'db.sqlite'}"

for d in [STORAGE_DIR, UPLOADS_DIR, CACHE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

AI_PROVIDER = os.getenv("SCRIPT_TOOL_AI_PROVIDER", "claude")
AI_MODEL = os.getenv("SCRIPT_TOOL_AI_MODEL", "claude-sonnet-4-6")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LOCAL_LLM_URL = os.getenv("SCRIPT_TOOL_LOCAL_LLM_URL", "http://localhost:8000/v1")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
MAX_PASTE_CHARS = 500_000
```

- [ ] **Step 3: 创建 app/main.py（最小入口）**

```python
from fastapi import FastAPI
from app.config import STORAGE_DIR, UPLOADS_DIR, CACHE_DIR

app = FastAPI(title="AI Script Tool", version="0.1.0")

@app.on_event("startup")
async def startup():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: 验证脚手架**

Run: `python -c "from app.main import app; print(app.title)"`
Expected: `AI Script Tool`

Run: `ls storage/`
Expected: 三个目录存在（忽略 db.sqlite）

- [ ] **Step 5: Commit**

```bash
git add requirements.txt app/
git commit -m "feat: project scaffold with FastAPI entry point and config"
```

---

### Task 2: 数据库模型

**Files:**
- Create: `app/models.py`
- Create: `app/db.py`

- [ ] **Step 1: 创建 app/db.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 2: 创建 app/models.py**

```python
import uuid
import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.db import Base

def _uid():
    return uuid.uuid4().hex[:12]

def _now():
    return datetime.now(timezone.utc).isoformat()

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=_uid)
    title = Column(String, nullable=False)
    source_novel = Column(String, default="")
    source_author = Column(String, default="")
    script_type = Column(String, default="other")
    config_json = Column(Text, default="{}")
    status = Column(String, default="draft")
    created_at = Column(String, default=_now)
    updated_at = Column(String, default=_now)

    pipeline_runs = relationship("PipelineRun", back_populates="project", cascade="all, delete-orphan")
    stage_caches = relationship("StageCache", back_populates="project", cascade="all, delete-orphan")

    def config(self):
        return json.loads(self.config_json) if self.config_json else {}

    def set_config(self, cfg: dict):
        self.config_json = json.dumps(cfg, ensure_ascii=False)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(String, primary_key=True, default=_uid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    current_stage = Column(Integer, default=0)
    stage_status_json = Column(Text, default="{}")
    error_message = Column(Text, default="")
    started_at = Column(String, default="")
    completed_at = Column(String, default="")

    project = relationship("Project", back_populates="pipeline_runs")


class StageCache(Base):
    __tablename__ = "stage_cache"

    id = Column(String, primary_key=True, default=_uid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    stage = Column(Integer, nullable=False)
    input_hash = Column(String, default="")
    output_json = Column(Text, default="{}")
    created_at = Column(String, default=_now)

    project = relationship("Project", back_populates="stage_caches")
```

- [ ] **Step 3: 验证数据库初始化**

```python
# 运行: python -c "
from app.db import init_db, SessionLocal
from app.models import Project, PipelineRun, StageCache
init_db()
db = SessionLocal()
print(f'Tables created, project count: {db.query(Project).count()}')
db.close()
"
```

Expected: `Tables created, project count: 0`

- [ ] **Step 4: Commit**

```bash
git add app/db.py app/models.py
git commit -m "feat: add SQLAlchemy models for projects, pipeline runs, stage cache"
```

---

### Task 3: AI Provider 接口与实现

**Files:**
- Create: `app/ai/__init__.py`
- Create: `app/ai/interface.py`
- Create: `app/ai/claude.py`
- Create: `app/ai/openai.py`
- Create: `app/ai/local.py`
- Create: `app/ai/factory.py`
- Create: `tests/__init__.py`
- Create: `tests/test_ai_provider.py`

- [ ] **Step 1: 创建 app/ai/interface.py**

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class AIProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system: str = "",
                       output_format: str = "json") -> str:
        ...

    @abstractmethod
    async def generate_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        ...

    @abstractmethod
    def model_name(self) -> str:
        ...
```

- [ ] **Step 2: 创建 app/ai/claude.py**

```python
from typing import AsyncIterator
from anthropic import AsyncAnthropic
from app.ai.interface import AIProvider
from app.config import ANTHROPIC_API_KEY

class ClaudeProvider(AIProvider):
    def __init__(self, model: str = "claude-sonnet-4-6"):
        self._model = model
        self._client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, system: str = "",
                       output_format: str = "json") -> str:
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": self._model, "max_tokens": 4096, "messages": messages}
        if system:
            kwargs["system"] = system
        response = await self._client.messages.create(**kwargs)
        return response.content[0].text

    async def generate_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": self._model, "max_tokens": 4096, "messages": messages}
        if system:
            kwargs["system"] = system
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
```

- [ ] **Step 3: 创建 app/ai/openai.py**

```python
from typing import AsyncIterator
from openai import AsyncOpenAI
from app.ai.interface import AIProvider
from app.config import OPENAI_API_KEY

class OpenAIProvider(AIProvider):
    def __init__(self, model: str = "gpt-4o"):
        self._model = model
        self._client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, system: str = "",
                       output_format: str = "json") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await self._client.chat.completions.create(
            model=self._model, messages=messages, max_tokens=4096
        )
        return response.choices[0].message.content or ""

    async def generate_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        stream = await self._client.chat.completions.create(
            model=self._model, messages=messages, max_tokens=4096, stream=True
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

- [ ] **Step 4: 创建 app/ai/local.py**

```python
from typing import AsyncIterator
from openai import AsyncOpenAI
from app.ai.interface import AIProvider
from app.config import LOCAL_LLM_URL

class LocalLLMProvider(AIProvider):
    def __init__(self, model: str = "local-model"):
        self._model = model
        self._client = AsyncOpenAI(base_url=LOCAL_LLM_URL, api_key="not-needed")

    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, system: str = "",
                       output_format: str = "json") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await self._client.chat.completions.create(
            model=self._model, messages=messages, max_tokens=4096
        )
        return response.choices[0].message.content or ""

    async def generate_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        stream = await self._client.chat.completions.create(
            model=self._model, messages=messages, max_tokens=4096, stream=True
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

- [ ] **Step 5: 创建 app/ai/factory.py**

```python
from app.ai.interface import AIProvider
from app.ai.claude import ClaudeProvider
from app.ai.openai import OpenAIProvider
from app.ai.local import LocalLLMProvider
from app.config import AI_PROVIDER, AI_MODEL

def create_ai_provider(provider: str = "", model: str = "") -> AIProvider:
    provider = provider or AI_PROVIDER
    model = model or AI_MODEL
    if provider == "claude":
        return ClaudeProvider(model=model)
    elif provider == "openai":
        return OpenAIProvider(model=model)
    elif provider == "local":
        return LocalLLMProvider(model=model)
    raise ValueError(f"Unknown AI provider: {provider}")
```

- [ ] **Step 6: 创建 tests/test_ai_provider.py（接口契约测试）**

```python
import pytest
from app.ai.interface import AIProvider
from app.ai.factory import create_ai_provider

def test_interface_is_abstract():
    with pytest.raises(TypeError):
        AIProvider()

def test_factory_creates_claude():
    p = create_ai_provider("claude", "claude-sonnet-4-6")
    assert isinstance(p, AIProvider)
    assert "claude" in p.model_name()

def test_factory_creates_openai():
    p = create_ai_provider("openai", "gpt-4o")
    assert isinstance(p, AIProvider)
    assert p.model_name() == "gpt-4o"

def test_factory_creates_local():
    p = create_ai_provider("local", "qwen")
    assert isinstance(p, AIProvider)

def test_factory_raises_on_unknown():
    with pytest.raises(ValueError, match="Unknown"):
        create_ai_provider("unknown")
```

- [ ] **Step 7: 运行测试验证**

Run: `pytest tests/test_ai_provider.py -v`
Expected: 5 tests pass

- [ ] **Step 8: Commit**

```bash
git add app/ai/ tests/
git commit -m "feat: add AI provider interface with Claude, OpenAI, and local implementations"
```

---

### Task 4: 流水线 Stage 0 — 文本预处理

**Files:**
- Create: `app/pipeline/__init__.py`
- Create: `app/pipeline/stage0_preprocess.py`
- Create: `tests/test_stage0.py`

- [ ] **Step 1: 创建 app/pipeline/stage0_preprocess.py**

```python
import re
from dataclasses import dataclass, field
from docx import Document
import markdown

@dataclass
class Chapter:
    index: int
    title: str
    content: str
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.content)

@dataclass
class PreprocessResult:
    title: str = ""
    chapters: list = field(default_factory=list)
    total_chars: int = 0
    errors: list = field(default_factory=list)

    def is_valid(self, min_chapters: int = 3) -> bool:
        return len(self.chapters) >= min_chapters and self.total_chars > 0


def preprocess_text(text: str) -> PreprocessResult:
    result = PreprocessResult()
    if not text.strip():
        result.errors.append("输入文本为空")
        return result

    result.title = _extract_title(text)
    chapters = _split_chapters(text)
    result.chapters = [Chapter(index=i, title=t, content=c)
                       for i, (t, c) in enumerate(chapters)]
    result.total_chars = sum(c.char_count for c in result.chapters)
    return result


def preprocess_docx(file_bytes: bytes) -> PreprocessResult:
    try:
        doc = Document(file_bytes)
        text = "\n".join(p.text for p in doc.paragraphs)
        return preprocess_text(text)
    except Exception as e:
        result = PreprocessResult()
        result.errors.append(f"docx 解析失败: {e}")
        return result


def preprocess_markdown(text: str) -> PreprocessResult:
    import markdown
    html = markdown.markdown(text)
    plain = re.sub(r'<[^>]+>', '', html)
    return preprocess_text(plain)


def _extract_title(text: str) -> str:
    first_line = text.strip().split("\n")[0].strip()
    first_line = re.sub(r'^[#\s]+', '', first_line)
    return first_line[:100] if len(first_line) <= 100 else first_line[:97] + "..."


def _split_chapters(text: str) -> list:
    patterns = [
        r'(?:^|\n)\s*(?:第[一二三四五六七八九十百千\d]+[章节回部卷])[：:\s]*[^\n]{0,50}',
        r'(?:^|\n)\s*(?:Chapter|CHAPTER|ch)\s*\d+[：:\s]*[^\n]{0,50}',
    ]
    for pattern in patterns:
        parts = re.split(pattern, text, flags=re.MULTILINE)
        titles = re.findall(pattern, text, flags=re.MULTILINE)
        if len(parts) > 1 and len(titles) >= 2:
            if parts[0].strip():
                titles.insert(0, "序言/前言")
            else:
                parts = parts[1:]
            return [(titles[i].strip(), parts[i].strip()) if i < len(titles)
                    else (f"第{i+1}章", parts[i].strip())
                    for i in range(len(parts))]

    chunks = _fallback_split(text, 3000)
    return [(f"第{i+1}节", chunk) for i, chunk in enumerate(chunks)]


def _fallback_split(text: str, chunk_size: int) -> list:
    paragraphs = text.split('\n\n')
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) > chunk_size and current:
            chunks.append(current.strip())
            current = p
        else:
            current += "\n\n" + p if current else p
    if current.strip():
        chunks.append(current.strip())
    return chunks if len(chunks) >= 3 else [text]
```

- [ ] **Step 2: 创建 tests/test_stage0.py**

```python
from app.pipeline.stage0_preprocess import preprocess_text, preprocess_docx, preprocess_markdown

SAMPLE_NOVEL = """
剑出华山

第一章 华山之巅

令狐冲站在华山之巅，望着脚下的云海。他已经在这里站了三个时辰。山风凛冽，吹得他的衣衫猎猎作响。

第二章 思过崖

思过崖上有一块巨石，巨石上刻满了剑招。令狐冲每日面壁，久而久之，那些剑招便刻在了他的心里。

第三章 不速之客

田伯光上山了。他带着一壶酒，说要和令狐冲比比剑法。令狐冲没有拒绝。

第四章 风清扬

崖后走出一位白发老者。
"""

def test_preprocess_extracts_title():
    result = preprocess_text(SAMPLE_NOVEL)
    assert result.title == "剑出华山"

def test_preprocess_splits_chapters():
    result = preprocess_text(SAMPLE_NOVEL)
    assert len(result.chapters) == 4
    assert result.chapters[0].title == "第一章 华山之巅"
    assert result.chapters[1].title == "第二章 思过崖"

def test_preprocess_counts_chars():
    result = preprocess_text(SAMPLE_NOVEL)
    result = preprocess_text(SAMPLE_NOVEL)
    assert result.total_chars > 0
    assert result.chapters[0].char_count == len(result.chapters[0].content)

def test_preprocess_empty_text():
    result = preprocess_text("")
    assert not result.is_valid()
    assert len(result.errors) > 0

def test_preprocess_requires_three_chapters():
    short = "第一章\n只有一章的内容。\n第二章\n第二章的内容。"
    result = preprocess_text(short)
    assert not result.is_valid(3)

def test_preprocess_markdown():
    md = "# 剑出华山\n\n## 第一章\n\n令狐冲站在山巅。\n\n## 第二章\n\n思过崖上。\n\n## 第三章\n\n田伯光上山。"
    result = preprocess_markdown(md)
    assert len(result.chapters) >= 3

def test_preprocess_fallback_split():
    text = "\n\n".join([f"段落{i} " * 500 for i in range(10)])
    result = preprocess_text(text)
    assert len(result.chapters) >= 3
```

- [ ] **Step 3: 运行测试验证**

Run: `pytest tests/test_stage0.py -v`
Expected: 7 tests pass

- [ ] **Step 4: Commit**

```bash
git add app/pipeline/ tests/test_stage0.py
git commit -m "feat: add Stage 0 text preprocessing with chapter splitting"
```

---

### Task 5: 流水线 Stage 1 — 分章节分析

**Files:**
- Create: `app/pipeline/stage1_chapter_analysis.py`
- Create: `tests/test_stage1.py`

- [ ] **Step 1: 创建 app/pipeline/stage1_chapter_analysis.py**

```python
import json
import asyncio
from dataclasses import dataclass, field
from app.ai.interface import AIProvider
from app.ai.factory import create_ai_provider
from app.pipeline.stage0_preprocess import Chapter

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

    response = await provider.generate(prompt, system=SYSTEM_PROMPT, output_format="json")
    return _parse_response(chapter.index, chapter.title, response)


async def analyze_chapters_parallel(chapters: list, provider: AIProvider = None) -> list:
    if provider is None:
        provider = create_ai_provider()
    tasks = [analyze_chapter(c, provider) for c in chapters]
    return await asyncio.gather(*tasks)


def _parse_response(index: int, title: str, response: str) -> ChapterAnalysis:
    analysis = ChapterAnalysis(chapter_index=index, chapter_title=title, raw_response=response)
    try:
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        data = json.loads(text)
        analysis.new_characters = data.get("new_characters", [])
        analysis.locations = data.get("locations", [])
        analysis.plot_events = data.get("plot_events", [])
        analysis.dialogue_excerpts = data.get("dialogue_excerpts", [])
    except (json.JSONDecodeError, KeyError):
        pass
    return analysis
```

- [ ] **Step 2: 创建 tests/test_stage1.py**

```python
import json
import pytest
from app.pipeline.stage0_preprocess import Chapter
from app.pipeline.stage1_chapter_analysis import analyze_chapter, _parse_response

SAMPLE_JSON = json.dumps({
    "new_characters": [
        {"name": "令狐冲", "aliases": ["冲哥"], "description": "华山派大弟子", "traits": ["洒脱"], "role_hint": "protagonist"}
    ],
    "locations": [
        {"name": "华山之巅", "description": "华山最高处", "time_hint": "清晨"}
    ],
    "plot_events": [
        {"summary": "令狐冲站在山巅", "importance": "minor", "characters_involved": ["令狐冲"]}
    ],
    "dialogue_excerpts": []
})

def test_parse_response_json():
    result = _parse_response(0, "第一章", SAMPLE_JSON)
    assert len(result.new_characters) == 1
    assert result.new_characters[0]["name"] == "令狐冲"
    assert len(result.locations) == 1
    assert len(result.plot_events) == 1

def test_parse_response_with_code_fence():
    fenced = f"```json\n{SAMPLE_JSON}\n```"
    result = _parse_response(0, "第一章", fenced)
    assert result.new_characters[0]["name"] == "令狐冲"

def test_parse_response_invalid_json():
    result = _parse_response(0, "第一章", "这不是合法的 JSON")
    assert result.raw_response == "这不是合法的 JSON"
    assert result.new_characters == []

def test_analyze_chapter_fields():
    chapter = Chapter(index=0, title="第一章 华山", content="令狐冲站在山巅。")
    analysis = _parse_response(0, "第一章 华山", SAMPLE_JSON)
    assert analysis.chapter_index == 0
    assert analysis.chapter_title == "第一章 华山"
    assert len(analysis.dialogue_excerpts) == 0
```

- [ ] **Step 3: 运行测试验证**

Run: `pytest tests/test_stage1.py -v`
Expected: 4 tests pass

- [ ] **Step 4: Commit**

```bash
git add app/pipeline/stage1_chapter_analysis.py tests/test_stage1.py
git commit -m "feat: add Stage 1 per-chapter analysis with parallel support"
```

---

### Task 6: 流水线 Stage 2 — 跨章节综合

**Files:**
- Create: `app/pipeline/stage2_cross_chapter_synthesis.py`
- Create: `tests/test_stage2.py`

- [ ] **Step 1: 创建 app/pipeline/stage2_cross_chapter_synthesis.py**

```python
import json
from dataclasses import dataclass, field
from app.ai.interface import AIProvider
from app.ai.factory import create_ai_provider
from app.pipeline.stage1_chapter_analysis import ChapterAnalysis

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
    try:
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        data = json.loads(text)
        result.characters = data.get("characters", [])
        result.relationships = data.get("relationships", [])
        result.locations = data.get("locations", [])
        result.main_plot = data.get("main_plot", "")
        result.subplots = data.get("subplots", [])
    except (json.JSONDecodeError, KeyError):
        pass
    return result
```

- [ ] **Step 2: 创建 tests/test_stage2.py**

```python
import json
from app.pipeline.stage2_cross_chapter_synthesis import synthesize, _parse_global

SAMPLE_GLOBAL = json.dumps({
    "characters": [
        {"name": "令狐冲", "aliases": ["冲哥"], "role": "protagonist", "description": "华山派大弟子", "traits": ["洒脱"], "first_appearance_chapter": 1},
        {"name": "岳不群", "aliases": [], "role": "antagonist", "description": "华山派掌门", "traits": ["深沉"], "first_appearance_chapter": 2}
    ],
    "relationships": [
        {"from": "令狐冲", "to": "岳不群", "type": "师徒", "description": "情同父子却有裂痕"}
    ],
    "locations": [
        {"name": "华山之巅", "description": "华山最高处", "chapters": [1]}
    ],
    "main_plot": "令狐冲在江湖历练中成长",
    "subplots": ["与岳不群的师徒关系破裂"]
})

def test_parse_global_characters():
    result = _parse_global(SAMPLE_GLOBAL)
    assert len(result.characters) == 2
    assert result.characters[0]["name"] == "令狐冲"

def test_parse_global_relationships():
    result = _parse_global(SAMPLE_GLOBAL)
    assert len(result.relationships) == 1
    assert result.relationships[0]["type"] == "师徒"

def test_parse_global_main_plot():
    result = _parse_global(SAMPLE_GLOBAL)
    assert "令狐冲" in result.main_plot

def test_parse_global_subplots():
    result = _parse_global(SAMPLE_GLOBAL)
    assert len(result.subplots) == 1

def test_parse_global_invalid():
    result = _parse_global("not json")
    assert result.characters == []
```

- [ ] **Step 3: 运行测试验证**

Run: `pytest tests/test_stage2.py -v`
Expected: 5 tests pass

- [ ] **Step 4: Commit**

```bash
git add app/pipeline/stage2_cross_chapter_synthesis.py tests/test_stage2.py
git commit -m "feat: add Stage 2 cross-chapter synthesis for character/plot merging"
```

---

### Task 7: 流水线 Stage 3 — 剧本结构设计

**Files:**
- Create: `app/pipeline/stage3_script_structure.py`
- Create: `tests/test_stage3.py`

- [ ] **Step 1: 创建 app/pipeline/stage3_script_structure.py**

```python
import json
from dataclasses import dataclass, field
from app.ai.interface import AIProvider
from app.ai.factory import create_ai_provider
from app.pipeline.stage2_cross_chapter_synthesis import GlobalAnalysis

@dataclass
class ScenePlan:
    id: str = ""
    act: int = 1
    episode: int = 1
    sequence: int = 1
    location: str = ""
    time: str = ""
    setting_description: str = ""
    characters_present: list = field(default_factory=list)
    summary: str = ""
    source_chapter: int = 0

@dataclass
class ScriptStructure:
    script_type: str = "film"
    scenes: list = field(default_factory=list)
    episode_summaries: list = field(default_factory=list)
    beat_sheet: list = field(default_factory=list)
    raw_response: str = ""

SYSTEM_PROMPT = """你是一位专业的剧本结构设计师。根据人物表、场景目录和情节分析，设计剧本的场景结构。输出 JSON。

输出格式：
{
  "scenes": [
    {"act": 1, "episode": 1, "sequence": 1, "location": "", "time": "", "setting_description": "", "characters_present": ["角色名"], "summary": "该场内容概述", "source_chapter": 1}
  ],
  "episode_summaries": [
    {"episode": 1, "title": "", "summary": "", "scene_indices": [0, 1, 2], "cliffhanger": ""}
  ],
  "beat_sheet": [
    {"beat": "开场画面/催化剂/中点/...", "scene_index": 0, "description": ""}
  ]
}

设计原则：
1. 每场通常 2-5 分钟（剧本 1 页 ≈ 1 分钟），合理分配
2. 关键情节事件必须有对应场景
3. 人物初次出场应安排单独的引入场景
4. 保持场景之间因果关系清晰"""


async def design_structure(global_analysis: GlobalAnalysis, config: dict,
                           provider: AIProvider = None) -> ScriptStructure:
    if provider is None:
        provider = create_ai_provider()

    prompt = f"""基于以下分析结果设计剧本结构：

剧本类型：{config.get('script_type', 'film')}
目标集数：{config.get('target_episodes', 'N/A')}
单集时长：{config.get('target_duration_per_episode', 'N/A')}
风格：{config.get('style', '通用')}

人物表：{json.dumps(global_analysis.characters, ensure_ascii=False)}
人物关系：{json.dumps(global_analysis.relationships, ensure_ascii=False)}
场景目录：{json.dumps(global_analysis.locations, ensure_ascii=False)}
主线：{global_analysis.main_plot}
支线：{json.dumps(global_analysis.subplots, ensure_ascii=False)}

请设计完整的场景列表。"""

    response = await provider.generate(prompt, system=SYSTEM_PROMPT, output_format="json")
    return _parse_structure(response, config.get("script_type", "film"))


def _parse_structure(response: str, script_type: str) -> ScriptStructure:
    result = ScriptStructure(script_type=script_type, raw_response=response)
    try:
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        data = json.loads(text)
        for i, s in enumerate(data.get("scenes", [])):
            result.scenes.append(ScenePlan(
                id=f"scene_{i+1:03d}",
                act=s.get("act", 1),
                episode=s.get("episode", 1),
                sequence=s.get("sequence", i+1),
                location=s.get("location", ""),
                time=s.get("time", ""),
                setting_description=s.get("setting_description", ""),
                characters_present=s.get("characters_present", []),
                summary=s.get("summary", ""),
                source_chapter=s.get("source_chapter", 0),
            ))
        result.episode_summaries = data.get("episode_summaries", [])
        result.beat_sheet = data.get("beat_sheet", [])
    except (json.JSONDecodeError, KeyError):
        pass
    return result
```

- [ ] **Step 2: 创建 tests/test_stage3.py**

```python
import json
from app.pipeline.stage3_script_structure import design_structure, _parse_structure

SAMPLE_STRUCTURE = json.dumps({
    "scenes": [
        {"act": 1, "episode": 1, "sequence": 1, "location": "华山之巅", "time": "清晨", "setting_description": "云雾缭绕", "characters_present": ["令狐冲"], "summary": "令狐冲出场", "source_chapter": 1},
        {"act": 1, "episode": 1, "sequence": 2, "location": "正气堂", "time": "日间", "setting_description": "庄严肃穆", "characters_present": ["令狐冲", "岳不群"], "summary": "师徒对峙", "source_chapter": 2}
    ],
    "episode_summaries": [
        {"episode": 1, "title": "剑气之争", "summary": "令狐冲回山", "scene_indices": [0, 1], "cliffhanger": "风清扬现身"}
    ],
    "beat_sheet": [
        {"beat": "开场画面", "scene_index": 0, "description": "华山之巅的孤寂"}
    ]
})

def test_parse_structure_scenes():
    result = _parse_structure(SAMPLE_STRUCTURE, "tv_series")
    assert len(result.scenes) == 2
    assert result.scenes[0].id == "scene_001"
    assert result.scenes[1].id == "scene_002"

def test_parse_structure_scene_fields():
    result = _parse_structure(SAMPLE_STRUCTURE, "film")
    s0 = result.scenes[0]
    assert s0.location == "华山之巅"
    assert s0.time == "清晨"
    assert s0.characters_present == ["令狐冲"]
    assert s0.summary != ""

def test_parse_structure_episode_summaries():
    result = _parse_structure(SAMPLE_STRUCTURE, "tv_series")
    assert len(result.episode_summaries) == 1
    assert result.episode_summaries[0]["title"] == "剑气之争"

def test_parse_structure_beat_sheet():
    result = _parse_structure(SAMPLE_STRUCTURE, "film")
    assert len(result.beat_sheet) == 1

def test_parse_structure_invalid():
    result = _parse_structure("bad", "film")
    assert result.scenes == []
```

- [ ] **Step 3: 运行测试验证**

Run: `pytest tests/test_stage3.py -v`
Expected: 5 tests pass

- [ ] **Step 4: Commit**

```bash
git add app/pipeline/stage3_script_structure.py tests/test_stage3.py
git commit -m "feat: add Stage 3 script structure design with scene planning"
```

---

### Task 8: 流水线 Stage 4 — 逐场内容生成 & Stage 5 — 组装校验

**Files:**
- Create: `app/pipeline/stage4_scene_generation.py`
- Create: `app/pipeline/stage5_assembly.py`
- Create: `tests/test_stage4.py`
- Create: `tests/test_stage5.py`

- [ ] **Step 1: 创建 app/pipeline/stage4_scene_generation.py**

```python
import json
import asyncio
from dataclasses import dataclass, field
from app.ai.interface import AIProvider
from app.ai.factory import create_ai_provider
from app.pipeline.stage3_script_structure import ScenePlan

@dataclass
class GeneratedScene:
    id: str = ""
    act: int = 1
    episode: int = 1
    sequence: int = 1
    location: str = ""
    time: str = ""
    setting_description: str = ""
    characters_present: list = field(default_factory=list)
    content: list = field(default_factory=list)
    raw_response: str = ""

SYSTEM_PROMPT = """你是一位专业的剧本作家。根据场景计划和人物信息，生成该场景的完整剧本内容。输出 JSON。

输出格式：
{
  "content": [
    {"type": "action", "text": "动作描述"},
    {"type": "dialogue", "character": "角色名", "text": "台词", "direction": "表演指示（可选）"},
    {"type": "transition", "text": "CUT TO:"},
    {"type": "note", "text": "备注"}
  ]
}

规则：
1. action 描述环境、动作、表情等视觉元素，使用现在时
2. dialogue 的 character 必须是人物表中存在的角色名
3. direction 是括号里的表演提示，可选
4. transition 仅用于场景切换，通常放在 content 末尾
5. 每场控制在 5-15 个 content 元素"""


async def generate_scene(plan: ScenePlan, characters: list,
                         original_text: str = "", provider: AIProvider = None) -> GeneratedScene:
    if provider is None:
        provider = create_ai_provider()

    scene_chars = [c for c in characters if c["name"] in plan.characters_present]
    char_desc = "\n".join(
        f"- {c['name']}（{c.get('role','')}）：{c.get('description','')}，性格：{', '.join(c.get('traits',[]))}"
        for c in scene_chars
    )

    prompt = f"""生成以下场景的剧本内容：

场景：{plan.id}
地点：{plan.location}
时间：{plan.time}
环境：{plan.setting_description}
出场人物：{', '.join(plan.characters_present)}
场景概要：{plan.summary}

人物信息：
{char_desc}

原始小说片段（参考）：
{original_text[:2000]}

请生成该场景的完整 content 数组。"""

    response = await provider.generate(prompt, system=SYSTEM_PROMPT, output_format="json")
    return _parse_scene(plan, response)


async def generate_scenes_parallel(plans: list, characters: list,
                                   chapter_texts: dict, provider: AIProvider = None) -> list:
    if provider is None:
        provider = create_ai_provider()
    tasks = [
        generate_scene(p, characters, chapter_texts.get(p.source_chapter, ""), provider)
        for p in plans
    ]
    return await asyncio.gather(*tasks)


def _parse_scene(plan: ScenePlan, response: str) -> GeneratedScene:
    scene = GeneratedScene(
        id=plan.id, act=plan.act, episode=plan.episode,
        sequence=plan.sequence, location=plan.location,
        time=plan.time, setting_description=plan.setting_description,
        characters_present=plan.characters_present,
        raw_response=response,
    )
    try:
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        data = json.loads(text)
        scene.content = data.get("content", [])
    except (json.JSONDecodeError, KeyError):
        pass
    return scene
```

- [ ] **Step 2: 创建 app/pipeline/stage5_assembly.py**

```python
import yaml
from dataclasses import dataclass, field
from app.pipeline.stage2_cross_chapter_synthesis import GlobalAnalysis
from app.pipeline.stage3_script_structure import ScriptStructure
from app.pipeline.stage4_scene_generation import GeneratedScene

@dataclass
class AssemblyResult:
    yaml_text: str = ""
    warnings: list = field(default_factory=list)
    is_valid: bool = False


def assemble(meta: dict, config: dict, global_analysis: GlobalAnalysis,
             structure: ScriptStructure, scenes: list) -> AssemblyResult:
    result = AssemblyResult()

    script = {
        "meta": meta,
        "config": config,
        "characters": _build_characters(global_analysis),
        "scenes": _build_scenes(scenes),
        "extensions": _build_extensions(config.get("script_type", "other"), structure),
    }

    result.yaml_text = yaml.dump(script, allow_unicode=True, default_flow_style=False,
                                  sort_keys=False, width=120)
    result.warnings = _validate(script)
    result.is_valid = len([w for w in result.warnings if w.startswith("ERROR")]) == 0
    return result


def _build_characters(ga: GlobalAnalysis) -> list:
    chars = []
    for i, c in enumerate(ga.characters):
        char = {
            "id": f"char_{i+1:03d}",
            "name": c.get("name", ""),
            "aliases": c.get("aliases", []),
            "role": c.get("role", "supporting"),
            "description": c.get("description", ""),
            "traits": c.get("traits", []),
            "relationships": [],
            "first_appearance_scene": "",
            "notes": "",
        }
        chars.append(char)

    name_to_id = {c["name"]: c["id"] for c in chars}
    for rel in ga.relationships:
        from_id = name_to_id.get(rel.get("from", ""))
        to_id = name_to_id.get(rel.get("to", ""))
        if from_id and to_id:
            for c in chars:
                if c["id"] == from_id:
                    c["relationships"].append({
                        "to": to_id,
                        "type": rel.get("type", ""),
                        "description": rel.get("description", ""),
                    })
    return chars


def _build_scenes(generated_scenes: list) -> list:
    scenes = []
    for gs in generated_scenes:
        scene = {
            "id": gs.id,
            "act": gs.act,
            "episode": gs.episode,
            "sequence": gs.sequence,
            "setting": {
                "location": gs.location,
                "time": gs.time,
                "description": gs.setting_description,
            },
            "characters_present": gs.characters_present,
            "content": gs.content,
            "page": None,
            "notes": "",
        }
        scenes.append(scene)
    return scenes


def _build_extensions(script_type: str, structure: ScriptStructure) -> dict:
    extensions = {}
    if script_type == "tv_series" and structure.episode_summaries:
        extensions["tv_series"] = {"episode_summaries": structure.episode_summaries}
    if script_type == "film" and structure.beat_sheet:
        extensions["film"] = {"beat_sheet": structure.beat_sheet}
    extensions["custom"] = {}
    return extensions


def _validate(script: dict) -> list:
    warnings = []
    if not script["meta"].get("title"):
        warnings.append("ERROR: 缺少剧本标题")
    if not script["scenes"]:
        warnings.append("ERROR: 没有场景内容")
    if not script["characters"]:
        warnings.append("WARNING: 人物表为空")

    char_ids = {c["id"] for c in script["characters"]}
    for scene in script["scenes"]:
        for elem in scene.get("content", []):
            if elem.get("type") == "dialogue":
                char_name = elem.get("character", "")
                if char_name and char_name not in char_ids:
                    warnings.append(f"WARNING: {scene['id']} 中台词归属未知角色 '{char_name}'")
    return warnings
```

- [ ] **Step 3: 创建 tests/test_stage4.py**

```python
import json
from app.pipeline.stage3_script_structure import ScenePlan
from app.pipeline.stage4_scene_generation import generate_scene, _parse_scene

SAMPLE_SCENE_JSON = json.dumps({
    "content": [
        {"type": "action", "text": "令狐冲步入正气堂，衣衫不整。"},
        {"type": "dialogue", "character": "岳不群", "text": "冲儿，你昨夜又去后山饮酒了？", "direction": "语重心长"},
        {"type": "action", "text": "令狐冲低头不语。"},
        {"type": "transition", "text": "CUT TO:"}
    ]
})

def test_parse_scene_content():
    plan = ScenePlan(id="scene_001", location="正气堂", time="清晨", characters_present=["令狐冲", "岳不群"])
    result = _parse_scene(plan, SAMPLE_SCENE_JSON)
    assert len(result.content) == 4
    assert result.content[0]["type"] == "action"
    assert result.content[1]["type"] == "dialogue"
    assert result.content[1]["character"] == "岳不群"
    assert result.content[3]["type"] == "transition"

def test_parse_scene_invalid():
    plan = ScenePlan(id="scene_001", location="", time="")
    result = _parse_scene(plan, "bad json")
    assert result.content == []
```

- [ ] **Step 4: 创建 tests/test_stage5.py**

```python
from app.pipeline.stage2_cross_chapter_synthesis import GlobalAnalysis
from app.pipeline.stage3_script_structure import ScriptStructure, ScenePlan
from app.pipeline.stage4_scene_generation import GeneratedScene
from app.pipeline.stage5_assembly import assemble

def make_fixtures():
    meta = {"title": "剑出华山", "source_novel": "笑傲江湖", "source_author": "金庸", "script_type": "tv_series", "version": "0.1.0", "created_at": "2026-06-05", "language": "zh-CN"}
    config = {"target_episodes": 40, "style": "武侠"}
    ga = GlobalAnalysis(
        characters=[
            {"name": "令狐冲", "role": "protagonist", "description": "华山派大弟子", "traits": ["洒脱"]},
            {"name": "岳不群", "role": "antagonist", "description": "华山派掌门", "traits": ["深沉"]},
        ],
        relationships=[{"from": "令狐冲", "to": "岳不群", "type": "师徒", "description": "情同父子"}]
    )
    structure = ScriptStructure(script_type="tv_series", episode_summaries=[
        {"episode": 1, "title": "剑气之争", "summary": "令狐冲回山"}
    ])
    gs1 = GeneratedScene(id="scene_001", act=1, episode=1, sequence=1, location="正气堂", time="清晨", characters_present=["令狐冲", "岳不群"],
        content=[
            {"type": "action", "text": "令狐冲步入正气堂。"},
            {"type": "dialogue", "character": "岳不群", "text": "冲儿，你又去饮酒了？", "direction": "失望"},
        ])
    return meta, config, ga, structure, [gs1]

def test_assemble_produces_valid_yaml():
    result = assemble(*make_fixtures())
    assert result.is_valid
    assert "剑出华山" in result.yaml_text
    assert "scene_001" in result.yaml_text

def test_assemble_includes_characters():
    result = assemble(*make_fixtures())
    assert "char_001" in result.yaml_text or "令狐冲" in result.yaml_text

def test_assemble_includes_extensions():
    result = assemble(*make_fixtures())
    assert "tv_series" in result.yaml_text or "episode_summaries" in result.yaml_text

def test_assemble_validation_no_title():
    meta, config, ga, structure, scenes = make_fixtures()
    meta["title"] = ""
    result = assemble(meta, config, ga, structure, scenes)
    assert not result.is_valid

def test_assemble_validation_no_scenes():
    meta, config, ga, structure, _ = make_fixtures()
    result = assemble(meta, config, ga, structure, [])
    assert not result.is_valid
```

- [ ] **Step 5: 运行测试验证**

Run: `pytest tests/test_stage4.py tests/test_stage5.py -v`
Expected: 7 tests pass

- [ ] **Step 6: Commit**

```bash
git add app/pipeline/stage4_scene_generation.py app/pipeline/stage5_assembly.py tests/test_stage4.py tests/test_stage5.py
git commit -m "feat: add Stage 4 scene generation and Stage 5 YAML assembly with validation"
```

---

### Task 9: 流水线执行器

**Files:**
- Create: `app/pipeline/executor.py`
- Create: `tests/test_executor.py`

- [ ] **Step 1: 创建 app/pipeline/executor.py**

```python
import json
import hashlib
import asyncio
from enum import Enum
from dataclasses import dataclass, field
from app.ai.interface import AIProvider
from app.ai.factory import create_ai_provider
from app.pipeline.stage0_preprocess import preprocess_text
from app.pipeline.stage1_chapter_analysis import analyze_chapters_parallel
from app.pipeline.stage2_cross_chapter_synthesis import synthesize
from app.pipeline.stage3_script_structure import design_structure
from app.pipeline.stage4_scene_generation import generate_scenes_parallel
from app.pipeline.stage5_assembly import assemble

class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"

@dataclass
class PipelineState:
    project_id: str = ""
    current_stage: int = 0
    stage_status: dict = field(default_factory=lambda: {i: StageStatus.PENDING.value for i in range(6)})
    stage_results: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    progress_callback: object = None

    def set_stage(self, stage: int, status: StageStatus):
        self.stage_status[stage] = status.value
        self.current_stage = stage


async def run_pipeline(project_id: str, text: str, meta: dict, config: dict,
                       provider: AIProvider = None,
                       progress_callback=None) -> PipelineState:
    if provider is None:
        provider = create_ai_provider()

    state = PipelineState(project_id=project_id, progress_callback=progress_callback)
    chapter_texts = {}

    try:
        # Stage 0
        state.set_stage(0, StageStatus.RUNNING)
        await _notify(state, "正在解析文本...")
        preprocess = preprocess_text(text)
        if not preprocess.is_valid():
            raise ValueError(f"文本章节不足（需要至少3章，检测到{len(preprocess.chapters)}章）")
        state.stage_results["preprocess"] = preprocess
        state.stage_results["meta"] = meta
        state.stage_results["config"] = config
        for ch in preprocess.chapters:
            chapter_texts[ch.index] = ch.content
        state.set_stage(0, StageStatus.DONE)

        # Stage 1
        state.set_stage(1, StageStatus.RUNNING)
        await _notify(state, f"正在分析 {len(preprocess.chapters)} 个章节...")
        chapter_analyses = await analyze_chapters_parallel(preprocess.chapters, provider)
        state.stage_results["chapter_analyses"] = chapter_analyses
        state.set_stage(1, StageStatus.DONE)

        # Stage 2
        state.set_stage(2, StageStatus.RUNNING)
        await _notify(state, "正在综合人物和情节...")
        global_analysis = await synthesize(chapter_analyses, provider)
        state.stage_results["global_analysis"] = global_analysis
        state.set_stage(2, StageStatus.DONE)

        # Stage 3
        state.set_stage(3, StageStatus.RUNNING)
        await _notify(state, "正在设计剧本结构...")
        structure = await design_structure(global_analysis, config, provider)
        state.stage_results["structure"] = structure
        state.set_stage(3, StageStatus.DONE)

        # Stage 4
        state.set_stage(4, StageStatus.RUNNING)
        await _notify(state, f"正在生成 {len(structure.scenes)} 场内容...")
        scenes = await generate_scenes_parallel(
            structure.scenes, global_analysis.characters, chapter_texts, provider
        )
        state.stage_results["scenes"] = scenes
        state.set_stage(4, StageStatus.DONE)

        # Stage 5
        state.set_stage(5, StageStatus.RUNNING)
        await _notify(state, "正在组装和校验 YAML...")
        result = assemble(meta, config, global_analysis, structure, scenes)
        state.stage_results["assembly"] = result
        if not result.is_valid:
            state.errors.extend(result.warnings)
        state.set_stage(5, StageStatus.DONE)

    except Exception as e:
        state.set_stage(state.current_stage, StageStatus.ERROR)
        state.errors.append(str(e))

    return state


def compute_input_hash(**kwargs) -> str:
    raw = json.dumps(kwargs, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def _notify(state: PipelineState, message: str):
    if state.progress_callback:
        await state.progress_callback({
            "project_id": state.project_id,
            "current_stage": state.current_stage,
            "stage_status": state.stage_status,
            "message": message,
        })
```

- [ ] **Step 2: 创建 tests/test_executor.py**

```python
from app.pipeline.executor import compute_input_hash

def test_compute_input_hash_deterministic():
    h1 = compute_input_hash(text="hello", stage=1)
    h2 = compute_input_hash(text="hello", stage=1)
    assert h1 == h2

def test_compute_input_hash_different():
    h1 = compute_input_hash(text="hello", stage=1)
    h2 = compute_input_hash(text="world", stage=1)
    assert h1 != h2
```

- [ ] **Step 3: 运行测试验证**

Run: `pytest tests/test_executor.py -v`
Expected: 2 tests pass

- [ ] **Step 4: Commit**

```bash
git add app/pipeline/executor.py tests/test_executor.py
git commit -m "feat: add pipeline executor with progress tracking and caching"
```

---

### Task 10: Web 路由 — 页面（SSR）

**Files:**
- Create: `app/routes/__init__.py`
- Create: `app/routes/pages.py`

- [ ] **Step 1: 创建 app/routes/pages.py**

```python
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Project

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    return request.app.state.templates.TemplateResponse("index.html", {
        "request": request, "projects": projects
    })

@router.get("/projects/new", response_class=HTMLResponse)
async def new_project(request: Request):
    return request.app.state.templates.TemplateResponse("project_new.html", {
        "request": request
    })

@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_workspace(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return request.app.state.templates.TemplateResponse("404.html", {
            "request": request, "message": "项目不存在"
        }, status_code=404)
    return request.app.state.templates.TemplateResponse("project.html", {
        "request": request, "project": project
    })

@router.get("/projects/{project_id}/stage/{stage}", response_class=HTMLResponse)
async def stage_review(project_id: str, stage: int, request: Request, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return request.app.state.templates.TemplateResponse("404.html", {
            "request": request, "message": "项目不存在"
        }, status_code=404)
    return request.app.state.templates.TemplateResponse("stage_review.html", {
        "request": request, "project": project, "stage": stage
    })

@router.get("/projects/{project_id}/script", response_class=HTMLResponse)
async def script_view(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return request.app.state.templates.TemplateResponse("404.html", {
            "request": request, "message": "项目不存在"
        }, status_code=404)
    return request.app.state.templates.TemplateResponse("script_view.html", {
        "request": request, "project": project
    })
```

- [ ] **Step 2: Commit**

```bash
git add app/routes/
git commit -m "feat: add SSR page routes for project list, workspace, and script view"
```

---

### Task 11: Web 路由 — API

**Files:**
- Create: `app/routes/api.py`

- [ ] **Step 1: 创建 app/routes/api.py**

```python
import json
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Project, PipelineRun, StageCache
from app.ai.factory import create_ai_provider
from app.pipeline.executor import run_pipeline

router = APIRouter(prefix="/api")

@router.post("/projects")
async def create_project(
    title: str = Form(...),
    source_novel: str = Form(""),
    source_author: str = Form(""),
    script_type: str = Form("other"),
    config_json: str = Form("{}"),
    db: Session = Depends(get_db),
):
    project = Project(
        title=title, source_novel=source_novel, source_author=source_author,
        script_type=script_type, config_json=config_json,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "title": project.title}

@router.post("/projects/{project_id}/upload")
async def upload_file(project_id: str, file: UploadFile = File(...),
                      db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    content = await file.read()
    filename = file.filename or "upload.txt"

    if filename.endswith(".docx"):
        from app.pipeline.stage0_preprocess import preprocess_docx
        result = preprocess_docx(content)
    elif filename.endswith(".md"):
        text = content.decode("utf-8", errors="replace")
        from app.pipeline.stage0_preprocess import preprocess_markdown
        result = preprocess_markdown(text)
    else:
        text = content.decode("utf-8", errors="replace")
        from app.pipeline.stage0_preprocess import preprocess_text
        result = preprocess_text(text)

    return {
        "filename": filename,
        "chapters": len(result.chapters),
        "total_chars": result.total_chars,
        "title": result.title,
        "errors": result.errors,
    }

@router.post("/projects/{project_id}/paste")
async def paste_text(project_id: str, request: Request,
                     db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    body = await request.json()
    text = body.get("text", "")
    if len(text) > 500_000:
        raise HTTPException(400, "文本超过 50 万字上限")

    from app.pipeline.stage0_preprocess import preprocess_text
    result = preprocess_text(text)

    return {
        "chapters": len(result.chapters),
        "total_chars": result.total_chars,
        "title": result.title,
        "errors": result.errors,
        "text": text,
    }

@router.post("/projects/{project_id}/run")
async def run_pipeline_endpoint(project_id: str, request: Request,
                                db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    body = await request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(400, "请先上传或粘贴小说文本")

    meta = {
        "title": project.title,
        "source_novel": project.source_novel,
        "source_author": project.source_author,
        "script_type": project.script_type,
        "version": "0.1.0",
        "created_at": project.created_at,
        "language": "zh-CN",
    }
    config = project.config()
    config["script_type"] = project.script_type

    run = PipelineRun(project_id=project_id)
    project.status = "processing"
    db.add(run)
    db.commit()

    async def event_stream():
        async def progress_callback(msg):
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

        state = await run_pipeline(project_id, text, meta, config,
                                   progress_callback=progress_callback)

        project.status = "done" if not state.errors else "error"
        db.commit()

        final_msg = {
            "status": "complete",
            "errors": state.errors,
            "yaml_text": state.stage_results.get("assembly").yaml_text if state.stage_results.get("assembly") else "",
        }
        yield f"data: {json.dumps(final_msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.get("/projects/{project_id}/script.yaml")
async def download_script(project_id: str, yaml_text: str = "",
                          db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    return PlainTextResponse(yaml_text, media_type="application/x-yaml",
                             headers={"Content-Disposition": f"attachment; filename={project.title}.yaml"})

@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    db.delete(project)
    db.commit()
    return {"deleted": project_id}
```

- [ ] **Step 2: Commit**

```bash
git add app/routes/api.py
git commit -m "feat: add REST API routes with SSE streaming for pipeline execution"
```

---

### Task 12: HTML 模板

**Files:**
- Create: `app/templates/base.html`
- Create: `app/templates/index.html`
- Create: `app/templates/project_new.html`
- Create: `app/templates/project.html`
- Create: `app/templates/stage_review.html`
- Create: `app/templates/script_view.html`
- Create: `app/templates/404.html`

- [ ] **Step 1: 创建 app/templates/base.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}AI 剧本创作工具{% endblock %}</title>
    <script src="https://unpkg.com/htmx.org@2.0.0"></script>
    <script src="https://unpkg.com/htmx.org@2.0.0/dist/ext/sse.js"></script>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <nav class="navbar">
        <a href="/" class="nav-brand">AI 剧本创作工具</a>
        <a href="/projects/new" class="nav-link">新建项目</a>
    </nav>
    <main class="container">
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

- [ ] **Step 2: 创建 app/templates/index.html**

```html
{% extends "base.html" %}
{% block title %}项目列表 — AI 剧本创作工具{% endblock %}
{% block content %}
<h1>我的项目</h1>
<div class="project-list">
    {% if projects %}
        {% for p in projects %}
        <div class="project-card">
            <h3><a href="/projects/{{ p.id }}">{{ p.title }}</a></h3>
            <span class="badge">{{ p.script_type }}</span>
            <span class="status {{ p.status }}">{{ p.status }}</span>
            <time>{{ p.updated_at[:10] }}</time>
        </div>
        {% endfor %}
    {% else %}
        <p class="empty">还没有项目。<a href="/projects/new">创建第一个</a></p>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 3: 创建 app/templates/project_new.html**

```html
{% extends "base.html" %}
{% block title %}新建项目 — AI 剧本创作工具{% endblock %}
{% block content %}
<h1>新建项目</h1>
<form hx-post="/api/projects" hx-target="#create-result" hx-swap="innerHTML">
    <label>项目名称 <input type="text" name="title" required></label>
    <label>来源小说 <input type="text" name="source_novel"></label>
    <label>原作者 <input type="text" name="source_author"></label>
    <label>剧本类型
        <select name="script_type">
            <option value="other">通用</option>
            <option value="film">电影</option>
            <option value="tv_series">电视剧</option>
            <option value="stage_play">舞台剧</option>
            <option value="animation">动画</option>
        </select>
    </label>
    <label>目标集数 (TV) <input type="number" name="config_json" value="{}" placeholder='{"target_episodes": 40}'></label>
    <button type="submit">创建项目</button>
</form>
<div id="create-result"></div>
{% endblock %}
```

- [ ] **Step 4: 创建 app/templates/project.html**

```html
{% extends "base.html" %}
{% block title %}{{ project.title }} — AI 剧本创作工具{% endblock %}
{% block content %}
<h1>{{ project.title }}</h1>
<div class="workspace">
    <div class="panel" id="upload-panel">
        <h2>1. 导入小说</h2>
        <form hx-encoding="multipart/form-data" hx-post="/api/projects/{{ project.id }}/upload" hx-target="#upload-result">
            <input type="file" name="file" accept=".txt,.docx,.md">
            <button type="submit">上传文件</button>
        </form>
        <hr>
        <textarea name="text" placeholder="或直接粘贴小说文本..." rows="10" style="width:100%"></textarea>
        <button hx-post="/api/projects/{{ project.id }}/paste" hx-include="previous textarea" hx-target="#upload-result">解析文本</button>
        <div id="upload-result"></div>
    </div>

    <div class="panel" id="pipeline-panel">
        <h2>2. 生成剧本</h2>
        <button id="run-btn" onclick="runPipeline()">一键生成剧本</button>
        <div id="progress">
            <div id="stage-0" class="stage">Stage 0: 文本预处理</div>
            <div id="stage-1" class="stage">Stage 1: 分章节分析</div>
            <div id="stage-2" class="stage">Stage 2: 跨章节综合</div>
            <div id="stage-3" class="stage">Stage 3: 剧本结构设计</div>
            <div id="stage-4" class="stage">Stage 4: 逐场内容生成</div>
            <div id="stage-5" class="stage">Stage 5: 组装 & 校验</div>
        </div>
    </div>

    <div class="panel" id="result-panel">
        <h2>3. 查看结果</h2>
        <a href="/projects/{{ project.id }}/script">查看/编辑剧本</a>
        <button onclick="downloadYAML()">下载 YAML</button>
    </div>
</div>

<script>
async function runPipeline() {
    document.getElementById('run-btn').disabled = true;
    const textarea = document.querySelector('textarea[name="text"]');
    const text = textarea.value;

    const res = await fetch('/api/projects/{{ project.id }}/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text}),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const msg = JSON.parse(line.slice(6));
                if (msg.message) {
                    const el = document.getElementById(`stage-${msg.current_stage}`);
                    if (el) el.textContent = `Stage ${msg.current_stage}: ${msg.message} [${msg.stage_status[msg.current_stage]}]`;
                }
                if (msg.status === 'complete') {
                    document.getElementById('run-btn').disabled = false;
                    if (msg.yaml_text) {
                        document.getElementById('result-panel').insertAdjacentHTML('beforeend',
                            `<pre style="max-height:400px;overflow:auto">${escapeHtml(msg.yaml_text.substring(0, 2000))}...</pre>`);
                    }
                }
            }
        }
    }
}

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function downloadYAML() {
    window.open('/api/projects/{{ project.id }}/script.yaml', '_blank');
}
</script>
{% endblock %}
```

- [ ] **Step 5: 创建 app/templates/stage_review.html**

```html
{% extends "base.html" %}
{% block title %}Stage {{ stage }} — {{ project.title }}{% endblock %}
{% block content %}
<h1>{{ project.title }} — Stage {{ stage }} 中间结果</h1>
<div id="stage-content" hx-get="/api/projects/{{ project.id }}/stage/{{ stage }}" hx-trigger="load">
    加载中...
</div>
<a href="/projects/{{ project.id }}">返回工作台</a>
{% endblock %}
```

- [ ] **Step 6: 创建 app/templates/script_view.html**

```html
{% extends "base.html" %}
{% block title %}剧本预览 — {{ project.title }}{% endblock %}
{% block content %}
<h1>{{ project.title }} — 剧本预览</h1>
<pre id="yaml-viewer" style="background:#1e1e1e;color:#d4d4d4;padding:1em;border-radius:4px;overflow:auto;max-height:80vh">
    剧本尚未生成，或从工作台查看已生成的结果。
</pre>
<a href="/projects/{{ project.id }}">返回工作台</a>
{% endblock %}
```

- [ ] **Step 7: 创建 app/templates/404.html**

```html
{% extends "base.html" %}
{% block title %}404{% endblock %}
{% block content %}
<h1>404</h1>
<p>{{ message or "页面不存在" }}</p>
<a href="/">返回首页</a>
{% endblock %}
```

- [ ] **Step 8: Commit**

```bash
git add app/templates/
git commit -m "feat: add Jinja2 HTML templates for all pages"
```

---

### Task 13: 静态文件 & 应用入口组装

**Files:**
- Create: `static/css/style.css`
- Modify: `app/main.py`

- [ ] **Step 1: 创建 static/css/style.css**

```css
:root {
    --bg: #fafafa;
    --fg: #1a1a1a;
    --accent: #2563eb;
    --border: #e5e5e5;
    --radius: 6px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--fg);
    line-height: 1.6;
}

.navbar {
    display: flex; align-items: center; gap: 1em;
    padding: 0.75em 1.5em; background: #fff; border-bottom: 1px solid var(--border);
}
.nav-brand { font-weight: 700; font-size: 1.1em; color: var(--fg); text-decoration: none; }
.nav-link { color: var(--accent); text-decoration: none; }

.container { max-width: 960px; margin: 0 auto; padding: 1.5em; }

h1 { margin-bottom: 0.75em; }

.project-card {
    display: flex; align-items: center; gap: 0.75em;
    padding: 0.75em 1em; margin-bottom: 0.5em;
    background: #fff; border: 1px solid var(--border); border-radius: var(--radius);
}
.project-card a { color: var(--accent); text-decoration: none; font-weight: 600; }
.project-card .badge { font-size: 0.8em; padding: 2px 8px; background: #e5e5e5; border-radius: 10px; }
.project-card .status.draft { color: #9ca3af; }
.project-card .status.processing { color: #f59e0b; }
.project-card .status.done { color: #10b981; }
.project-card .status.error { color: #ef4444; }

.panel {
    background: #fff; border: 1px solid var(--border); border-radius: var(--radius);
    padding: 1em; margin-bottom: 1em;
}
.panel h2 { font-size: 1em; margin-bottom: 0.5em; }

label { display: block; margin-bottom: 0.5em; font-weight: 500; }
input, select, textarea {
    width: 100%; padding: 0.5em; margin-top: 0.25em;
    border: 1px solid var(--border); border-radius: var(--radius);
    font-size: 0.95em;
}
button {
    padding: 0.5em 1.25em; background: var(--accent); color: #fff;
    border: none; border-radius: var(--radius); cursor: pointer; font-size: 0.95em;
}
button:disabled { opacity: 0.6; cursor: not-allowed; }
button:hover:not(:disabled) { filter: brightness(1.1); }

.stage { padding: 0.25em 0; color: #9ca3af; font-size: 0.9em; }
.stage.active { color: var(--accent); font-weight: 600; }
.stage.done { color: #10b981; }
.stage.error { color: #ef4444; }

.empty { color: #9ca3af; margin-top: 1em; }
```

- [ ] **Step 2: 更新 app/main.py（组装所有路由和模板）**

```python
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import STORAGE_DIR, UPLOADS_DIR, CACHE_DIR
from app.db import init_db

app = FastAPI(title="AI Script Tool", version="0.1.0")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
app.state.templates = templates

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

from app.routes.pages import router as pages_router
from app.routes.api import router as api_router
app.include_router(pages_router)
app.include_router(api_router)

@app.on_event("startup")
async def startup():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 3: 验证应用可启动**

Run: `python -c "from app.main import app; print(f'Routes: {len(app.routes)}')"`
Expected: `Routes: N` (N ≥ 10)

- [ ] **Step 4: Commit**

```bash
git add static/ app/main.py
git commit -m "feat: add CSS styles, wire up routes and templates in main.py"
```

---

### Task 14: README & 最终验证

**Files:**
- Create: `README.md`

- [ ] **Step 1: 创建 README.md**

````markdown
# AI 辅助剧本创作工具

将 3 章以上小说文本自动转换为结构化剧本（YAML 格式）。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 设置 AI API Key（至少选一个）
export ANTHROPIC_API_KEY="sk-ant-..."    # Claude
export OPENAI_API_KEY="sk-..."          # GPT
# 或设置本地模型
export SCRIPT_TOOL_AI_PROVIDER="local"
export SCRIPT_TOOL_LOCAL_LLM_URL="http://localhost:8000/v1"

# 启动
uvicorn app.main:app --reload
```

访问 http://localhost:8000

## 使用流程

1. **新建项目** → 填写剧本元信息
2. **导入小说** → 上传 .txt/.docx/.md 文件或粘贴文本（需 ≥ 3 章）
3. **一键生成** → AI 自动完成 6 阶段转化
4. **查看/编辑** → 在线预览剧本，下载 YAML 文件

## 中间结果干预

在流水线面板中，Stage 1/2/3 完成后可暂停查看中间结果：
- Stage 1：审核 AI 识别的人物和场景
- Stage 2：调整人物关系和情节线
- Stage 3：调整场景结构和分集

## 项目结构

```
app/
├── main.py              # FastAPI 入口
├── config.py            # 配置
├── db.py                # 数据库连接
├── models.py            # ORM 模型
├── routes/
│   ├── pages.py         # SSR 页面路由
│   └── api.py           # REST API + SSE
├── pipeline/
│   ├── executor.py      # 流水线调度
│   ├── stage0_preprocess.py
│   ├── stage1_chapter_analysis.py
│   ├── stage2_cross_chapter_synthesis.py
│   ├── stage3_script_structure.py
│   ├── stage4_scene_generation.py
│   └── stage5_assembly.py
├── ai/
│   ├── interface.py     # AI 抽象接口
│   ├── claude.py
│   ├── openai.py
│   ├── local.py
│   └── factory.py
└── templates/
    ├── base.html
    ├── index.html
    ├── project_new.html
    ├── project.html
    ├── stage_review.html
    └── script_view.html
```
````

- [ ] **Step 2: 运行全部测试**

Run: `pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with quickstart and usage guide"
```

---

## 实施顺序

```
Task 1  (脚手架)        ──┐
Task 2  (数据模型)       │  基础设施，必须先完成
Task 3  (AI Provider)   ──┘
Task 4  (Stage 0)       ──┐
Task 5  (Stage 1)        │
Task 6  (Stage 2)        ├─ 流水线，按 Stage 顺序
Task 7  (Stage 3)        │
Task 8  (Stages 4+5)     │
Task 9  (Executor)      ──┘
Task 10 (SSR Routes)    ──┐
Task 11 (API Routes)     ├─ Web 层，依赖流水线完成
Task 12 (Templates)      │
Task 13 (Static + Main) ──┘
Task 14 (README + Verify) ── 最终收尾
```

Tasks 1-3 可先并行，但鉴于依赖关系（AI Provider 接口被流水线使用），建议按编号顺序执行。
