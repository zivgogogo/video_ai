# AI 辅助剧本创作工具 — 设计文档

**日期**: 2026-06-05
**状态**: 设计完成，待实施

## 概述

将 3 章以上小说文本自动转换为结构化剧本（YAML 格式），让作者快速获得可编辑、可打磨的剧本初稿。

## 需求总结

| 维度 | 决策 |
|------|------|
| 剧本类型 | 通用可扩展 Schema，覆盖电影/电视剧/舞台剧/动画 |
| 工作流 | 混合模式（默认一键生成 + 可分步干预） |
| 产品形态 | Web 应用（FastAPI + SSR + SQLite） |
| AI 后端 | API 优先（Claude/GPT），接口抽象支持本地模型替换 |
| 输入格式 | 文件上传（txt/docx/md）+ 在线粘贴编辑 |

## 项目结构

```
script-tool/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── routes/
│   │   ├── pages.py         # SSR 页面路由 (Jinja2)
│   │   └── api.py           # REST API + SSE
│   ├── models.py            # SQLAlchemy 模型
│   ├── pipeline/
│   │   ├── executor.py      # 流水线调度器
│   │   ├── stage0_preprocess.py
│   │   ├── stage1_chapter_analysis.py
│   │   ├── stage2_cross_chapter_synthesis.py
│   │   ├── stage3_script_structure.py
│   │   ├── stage4_scene_generation.py
│   │   └── stage5_assembly.py
│   ├── ai/
│   │   ├── interface.py     # AI Provider 抽象接口
│   │   ├── claude.py        # Claude API 实现
│   │   ├── openai.py        # GPT API 实现
│   │   └── local.py         # 本地模型实现
│   └── templates/
│       ├── base.html
│       ├── index.html
│       ├── project.html     # 项目工作台
│       ├── stage_review.html # 中间结果查看/编辑
│       └── script_view.html # 剧本预览 & YAML 编辑器
├── static/
│   ├── css/
│   └── js/                  # 少量 JS (HTMX + SSE)
├── storage/                 # 运行时数据
│   ├── db.sqlite
│   ├── uploads/
│   └── cache/               # Stage 缓存
├── requirements.txt
├── schema/
│   └── script-yaml-schema.md  # YAML Schema 规范文档
└── README.md
```

## 架构

### Web 层

```
浏览器 (Jinja2 SSR + HTMX)
    │
    ▼
FastAPI
├── 页面路由 (SSR)    → HTML 页面
├── API 路由 (REST)   → JSON 响应
└── SSE 端点          → 流式状态推送 (流水线进度/AI 生成过程)
    │
    ▼
SQLite (projects, pipeline_runs, stage_cache)
```

### 流水线架构

```
Stage 0: 文本预处理   (纯工程)
    │
Stage 1: 分章节分析   (LLM × N 章，可并行)  ◀── 暂停点
    │
Stage 2: 跨章节综合   (LLM × 1)            ◀── 暂停点
    │
Stage 3: 剧本结构设计  (LLM × 1)            ◀── 暂停点
    │
Stage 4: 逐场内容生成  (LLM × N 场，可并行)
    │
Stage 5: 组装 & 校验   (纯工程)
    │
script.yaml
```

每个 Stage 输出落盘缓存，相同输入不重复调用 AI。

### AI Provider 接口

```python
class AIProvider(ABC):
    """所有 AI 后端实现此接口"""

    @abstractmethod
    async def generate(self, prompt: str, system: str,
                       output_format: str = "json") -> str:
        ...

    @abstractmethod
    async def generate_stream(self, prompt: str, system: str) -> AsyncIterator[str]:
        ...

    @abstractmethod
    def model_name(self) -> str:
        ...
```

实现类：`ClaudeProvider`, `OpenAIProvider`, `LocalLLMProvider`。

配置方式：环境变量或 UI 设置页切换。

### 数据库模型

```sql
projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_novel TEXT,
    source_author TEXT,
    script_type TEXT DEFAULT 'other',
    config_json TEXT,
    status TEXT DEFAULT 'draft',  -- draft/processing/done/error
    created_at TEXT,
    updated_at TEXT
)

pipeline_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),
    current_stage INTEGER DEFAULT 0,
    stage_status_json TEXT,  -- {"0": "done", "1": "running", ...}
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT
)

stage_cache (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    stage INTEGER,
    input_hash TEXT,  -- SHA256 of inputs, 用于缓存命中
    output_json TEXT,
    created_at TEXT
)
```

## 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| SSR 而非 SPA | Jinja2 + HTMX | 作者群体不需要 SPA 的复杂交互，SSR 开发速度快、部署简单 |
| SQLite 而非 PostgreSQL | SQLite | 单用户工具，无并发压力，零运维 |
| 文件缓存而非 Redis | 文件系统 | 缓存粒度是 Stage 级别，读写频率低，文件系统足够 |
| 流水线而非单次调用 | 6 阶段流水线 | 控制质量、支持分步干预、并行章节处理 |
| 暂停点设计 | Stage 1/2/3 后可暂停 | 人物识别和结构设计是最需要人工介入的环节 |
| SSE 而非 WebSocket | SSE | 单向推送（服务端→客户端），比 WebSocket 简单，足够用 |

## 非功能需求

- **一次性处理上限**: 建议 20 章、50 万字以内；超出建议分批处理
- **响应时间**: Stage 0 < 5s；每个 LLM 调用 5-30s；并行加速后完整流程 2-5 分钟
- **API 成本**: 单次完整转换（10 章小说 → 30 场剧本）预估约 $2-5（Claude Opus）或 $0.5-1（GPT-4o）
- **文件大小上限**: 上传文件 10MB；在线粘贴 50 万字

## 待定事项

- 用户认证（MVP 阶段暂不需要，单用户即可）
- 多用户支持（如果有需求，后续加简单的 API Key 认证）
- 剧本导出格式（YAML 是核心格式，后续可导出 PDF/Fountain）
- 协作编辑（不在 MVP 范围内）
