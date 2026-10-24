视频介绍：
【七牛云☁竞赛视频-哔哩哔哩】 https://b23.tv/AqzOm9g
七牛云☁竞赛视频 # 七牛云 # aicoding... https://v.douyin.com/09iMpaV-8JA/

# 🎬 AI 剧本创作工具

将小说文本（≥3 章）自动转换为**结构化 YAML 剧本**和**行业标准格式剧本**，支持电影、电视剧、舞台剧、动画等多种类型。

---

## 目录

- [功能概览](#功能概览)
- [项目架构](#项目架构)
- [环境搭建](#环境搭建)
- [API Key 配置详解](#api-key-配置详解)
- [使用指南](#使用指南)
- [6 阶段流水线详解](#6-阶段流水线详解)
- [功能模块说明](#功能模块说明)
- [API 接口文档](#api-接口文档)
- [常见问题](#常见问题)
- [开发指南](#开发指南)

---

## 功能概览

### 核心功能

| 模块 | 说明 |
|------|------|
| 📂 **文件导入** | 支持 `.txt` / `.docx` / `.md` 格式上传，或直接粘贴小说文本（最多 50 万字） |
| ⚡ **一键生成** | 6 阶段全自动流水线，从文本解析到剧本导出全程 AI 驱动 |
| 📋 **分步生成** | 逐阶段执行，每步可暂停审查 AI 中间结果（人物、情节、场景结构） |
| 🕸 **场景编排看板** | Stage 3 完成后提供拖拽式场景看板，自由增删合并拆分场景 |
| 📝 **在线编辑** | 生成的剧本支持在线预览和编辑，实时保存 |
| ⬇ **多格式导出** | 支持 YAML（结构化数据）和 PDF（行业标准排版）双格式导出 |
| 💬 **AI 助手** | 右下角聊天面板，支持翻译、润色、摘要等快捷操作，5 种模型自由切换 |
| 🔄 **断点续传** | 每阶段结果自动缓存，重新开始或切换模型后已完成阶段无需重跑 |

### 支持的剧本类型

- 电影剧本（Film）
- 电视剧剧本（TV Series）— 支持多集场景编排
- 动画剧本（Animation）
- 舞台剧剧本（Stage Play）
- 自定义（Custom）

---

## 项目架构

```
script-tool/
├── app/
│   ├── main.py                  # FastAPI 入口，挂载静态文件与路由
│   ├── config.py                # 配置中心：环境变量加载、路径管理
│   ├── models.py                # 数据模型：Project / PipelineRun / StageCache
│   ├── db.py                    # SQLite 数据库引擎与会话管理
│   │
│   ├── ai/                      # AI 后端抽象层（5 种 Provider）
│   │   ├── interface.py         # AIProvider 抽象接口
│   │   ├── factory.py           # Provider 工厂函数
│   │   ├── claude.py            # Anthropic Claude API
│   │   ├── openai.py            # OpenAI GPT (兼容自定义 base_url)
│   │   ├── deepseek.py          # DeepSeek (OpenAI 兼容协议)
│   │   ├── gemini.py            # Google Gemini
│   │   └── local.py             # 本地模型 (LM Studio / Ollama)
│   │
│   ├── pipeline/                # 6 阶段流水线引擎
│   │   ├── executor.py          # 流水线调度器（含缓存、进度、重试逻辑）
│   │   ├── stage0_preprocess.py # Stage 0: 文本预处理（章节拆分）
│   │   ├── stage1_chapter_analysis.py  # Stage 1: 分章节分析
│   │   ├── stage2_cross_chapter_synthesis.py  # Stage 2: 跨章节综合
│   │   ├── stage3_script_structure.py    # Stage 3: 剧本结构设计
│   │   ├── stage4_scene_generation.py    # Stage 4: 逐场内容生成
│   │   ├── stage5_assembly.py    # Stage 5: YAML 组装 & 标准格式转换
│   │   ├── pdf_export.py        # PDF 导出（行业标准排版）
│   │   └── utils.py             # JSON 提取等工具函数
│   │
│   ├── routes/                  # HTTP 路由层
│   │   ├── pages.py             # 页面路由（Jinja2 SSR）
│   │   ├── api.py               # REST API + SSE 流式接口
│   │   └── chat.py              # AI 助手聊天接口
│   │
│   └── templates/               # Jinja2 模板
│       ├── base.html            # 基础布局（导航栏、粒子背景）
│       ├── index.html           # 首页（项目列表）
│       ├── project_new.html     # 新建项目
│       ├── project.html         # 项目工作台（核心页面）
│       ├── stage_review.html    # 中间结果审查
│       ├── stage3_kanban.html   # 场景编排看板
│       ├── character_graph.html # 人物关系图谱
│       └── script_view.html     # 在线剧本查看/编辑
│
├── static/
│   ├── css/style.css            # 全局样式（暗色科技主题）
│   ├── js/
│   │   ├── htmx.min.js          # HTMX 前端交互库
│   │   └── particles.js         # 粒子背景动画
│   └── img/
│       └── logo.svg             # 品牌 Logo
│
├── storage/                     # 运行时数据（自动创建）
│   ├── texts/                   # 上传的文本文件
│   ├── cache/                   # 流水线缓存
│   └── db.sqlite                # SQLite 数据库
│
├── requirements.txt             # Python 依赖
├── .env.example                 # 配置文件模板
├── start.sh                     # 一键启动脚本
└── README.md
```

### 技术栈

| 层级 | 技术 |
|------|------|
| **Web 框架** | FastAPI + Uvicorn (ASGI) |
| **模板引擎** | Jinja2 (SSR 渲染) |
| **前端交互** | HTMX 2.0 (无刷新局部更新) + 原生 JavaScript |
| **数据库** | SQLite + SQLAlchemy ORM |
| **AI 后端** | Claude / GPT / DeepSeek / Gemini / 本地模型 |
| **PDF 生成** | fpdf2 (Courier 12pt + SimSun 中文字体) |
| **文件解析** | python-docx + markdown |
| **异步** | Python asyncio (流式 SSE 推送) |

---

## 环境搭建

### 前置要求

- **Python 3.10+**（推荐 3.12）
- **pip**（Python 包管理器）
- **Git**（可选，用于克隆仓库）

### 步骤 1：克隆项目

```bash
git clone https://github.com/ailakala/script-tool.git
cd script-tool
```

如果不想用 Git，也可以直接下载 ZIP 包解压。

### 步骤 2：创建虚拟环境（推荐）

```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

> 虚拟环境可以隔离项目依赖，避免与系统 Python 包冲突。如果不想用虚拟环境，可以跳过此步。

### 步骤 3：安装依赖

```bash
pip install -r requirements.txt
```

如果安装较慢，可以使用国内镜像：

```bash
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

<details>
<summary>完整依赖列表（点击展开）</summary>

| 包名 | 版本 | 用途 |
|------|------|------|
| `fastapi` | 0.115 | Web 框架 |
| `uvicorn[standard]` | 0.30 | ASGI 服务器 |
| `sqlalchemy` | 2.0 | ORM 数据库 |
| `jinja2` | 3.1 | 模板引擎 |
| `python-multipart` | 0.0.12 | 文件上传 |
| `anthropic` | 0.40 | Claude API SDK |
| `openai` | 1.60 | OpenAI/DeepSeek 兼容 SDK |
| `google-genai` | 1.14 | Gemini API SDK |
| `python-docx` | 1.1 | Word 文档解析 |
| `markdown` | 3.7 | Markdown 解析 |
| `pyyaml` | 6.0 | YAML 序列化 |
| `fpdf2` | 2.8 | PDF 生成 |
| `python-dotenv` | 1.1 | 环境变量管理 |
| `pytest` | 8.3 | 测试框架 |
| `httpx` | 0.28 | HTTP 测试客户端 |

</details>

### 步骤 4：配置环境变量

```bash
# 从模板创建配置文件
cp .env.example .env
```

编辑 `.env` 文件，至少需要配置一个 AI 后端的 API Key。详细说明见下一节。

### 步骤 5：启动服务

**方式一：一键启动脚本**

```bash
bash start.sh
```

脚本会自动：
1. 检测首次运行 → 提示编辑 `.env`
2. 检测跨文件系统环境（WSL / Git Bash）→ 自动重定向数据库路径
3. 安装缺失的依赖
4. 启动 Uvicorn 服务器

**方式二：手动启动**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 访问 http://localhost:8000
```

**方式三：开发模式启动（支持热重载）**

```bash
# Windows
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# macOS / Linux
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

打开浏览器访问 **http://localhost:8000**。

### 各系统特别注意

<details>
<summary>🪟 Windows 用户</summary>

- 推荐使用 **PowerShell** 或 **Git Bash**
- 如果使用 Git Bash，启动脚本会自动检测环境，将 SQLite 数据库重定向到 `C:/Users/<用户名>/script_tool.db`
- 如果手动启动遇到 `database is locked` 错误，请在 `.env` 中设置：
  ```
  SCRIPT_TOOL_DATABASE_URL=sqlite:///C:/Users/你的用户名/script_tool.db
  ```

</details>

<details>
<summary>🐧 WSL (Windows Subsystem for Linux) 用户</summary>

WSL 跨文件系统访问 Windows 路径时，SQLite 无法正常加锁。解决方案：

1. **方式一**：在 `.env` 中设置 Windows 本机路径
   ```
   SCRIPT_TOOL_DATABASE_URL=sqlite:///C:/Users/你的用户名/script_tool.db
   ```
2. **方式二**：使用 `start.sh` 启动，脚本自动检测并配置

</details>

<details>
<summary>🍎 macOS 用户</summary>

- macOS 自带 Python 可能版本较旧，建议用 Homebrew 安装：
  ```bash
  brew install python@3.12
  ```
- 如果 PDF 生成缺少中文字体，可安装：
  ```bash
  brew install --cask font-simsun
  ```

</details>

---

## API Key 配置详解

整个项目的 AI 能力依赖于 **两大块配置**：流水线剧本生成 和 AI 助手聊天。两者**共用同一套 API Key**，但可以独立配置不同模型。

### 配置文件的加载机制

1. 项目启动时，`app/config.py` 自动读取项目根目录的 `.env` 文件
2. 所有配置通过环境变量注入，不硬编码在代码中
3. 环境变量名统一前缀 `SCRIPT_TOOL_` 避免与其他应用冲突

### 一、流水线剧本生成的 API Key

流水线是**自动化的 6 阶段 AI 流程**，每次调用消耗大量 tokens。通过以下两个核心变量控制：

```
SCRIPT_TOOL_AI_PROVIDER=claude        # 选择哪个 AI 后端
SCRIPT_TOOL_AI_MODEL=claude-sonnet-4-6  # 具体模型名
```

然后根据你选择的 `SCRIPT_TOOL_AI_PROVIDER`，配置对应的 API Key：

#### 方案 A：Claude API（推荐）

最推荐的选择，中文理解和创意写作能力最强，剧本质量最高。

```bash
SCRIPT_TOOL_AI_PROVIDER=claude
SCRIPT_TOOL_AI_MODEL=claude-sonnet-4-6
SCRIPT_TOOL_ANTHROPIC_API_KEY=sk-ant-api03-你的密钥
```

| 获取地址 | 费用参考 |
|---------|---------|
| [console.anthropic.com](https://console.anthropic.com/settings/keys) | $2-5/次完整生成 |

> **模型选择建议**：
> - `claude-sonnet-4-6`：性价比最优，推荐日常使用
> - `claude-opus-4-8`：最强质量，长篇小说或复杂剧本
> - `claude-haiku-4-5`：最快速度，用于测试或简单任务

#### 方案 B：OpenAI GPT

```bash
SCRIPT_TOOL_AI_PROVIDER=openai
SCRIPT_TOOL_AI_MODEL=gpt-4o
SCRIPT_TOOL_OPENAI_API_KEY=sk-proj-你的密钥
```

| 获取地址 | 费用参考 |
|---------|---------|
| [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | $0.5-1/次完整生成 |

> 如果你的 OpenAI Key 是通过**第三方代理/中转服务**获取的，需要额外设置：
> ```bash
> SCRIPT_TOOL_OPENAI_BASE_URL=https://你的代理地址/v1
> ```
> 这个配置也适用于任何 OpenAI 兼容接口（如 Azure OpenAI、OneAPI 等）。

#### 方案 C：DeepSeek（性价比之选）

中文优秀，价格极低，国内网络直连。

```bash
SCRIPT_TOOL_AI_PROVIDER=deepseek
SCRIPT_TOOL_AI_MODEL=deepseek-chat
SCRIPT_TOOL_DEEPSEEK_API_KEY=sk-你的密钥
```

| 获取地址 | 费用参考 |
|---------|---------|
| [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) | ¥0.5-1/次完整生成 |

> 可选模型：`deepseek-chat`（通用）、`deepseek-reasoner`（推理增强，创意写作更佳）。通过 `SCRIPT_TOOL_DEEPSEEK_MODEL` 切换。

#### 方案 D：Google Gemini

免费额度友好，适合测试和轻度使用。

```bash
SCRIPT_TOOL_AI_PROVIDER=gemini
SCRIPT_TOOL_AI_MODEL=gemini-2.5-flash
SCRIPT_TOOL_GEMINI_API_KEY=你的密钥
```

| 获取地址 | 费用参考 |
|---------|---------|
| [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | 免费/接近免费 |

> 可选模型：`gemini-2.5-pro`（最强）、`gemini-2.5-flash`（快速推荐）。通过 `SCRIPT_TOOL_GEMINI_MODEL` 切换。

#### 方案 E：本地模型（免费，完全离线）

支持 LM Studio 和 Ollama，数据完全本地处理。

```bash
SCRIPT_TOOL_AI_PROVIDER=local
SCRIPT_TOOL_AI_MODEL=qwen2.5-7b-instruct
```

| 工具 | 下载地址 | 推荐模型 |
|------|---------|---------|
| LM Studio | [lmstudio.ai](https://lmstudio.ai) | Qwen 2.5 7B / 14B |
| Ollama | [ollama.com](https://ollama.com) | qwen2.5:7b / deepseek-r1:7b |

> LM Studio 设置：加载模型 → Developer 标签 → Start Server（默认端口 1234），无需额外配置。
>
> Ollama 用户需修改端口：
> ```bash
> SCRIPT_TOOL_LOCAL_LLM_URL=http://localhost:11434/v1
> ```

---

### 二、AI 助手的 API Key

项目页面右下角的 💬 **AI 助手聊天面板**支持 5 种模型**实时切换**，无需重启服务。

它的 API Key 配置与流水线使用**同一套环境变量**——只要你配置了哪个 Provider 的 Key，聊天面板中切换过去就能用。

```bash
# Claude — 和流水线共用这个 Key
SCRIPT_TOOL_ANTHROPIC_API_KEY=sk-ant-api03-你的密钥

# GPT (OpenAI) — 和流水线共用这个 Key
SCRIPT_TOOL_OPENAI_API_KEY=sk-proj-你的密钥
# 可选：自定义 API 地址（如中转/代理）
SCRIPT_TOOL_OPENAI_BASE_URL=https://你的代理地址/v1

# DeepSeek — 和流水线共用这个 Key
SCRIPT_TOOL_DEEPSEEK_API_KEY=sk-你的密钥

# Gemini — 和流水线共用这个 Key
SCRIPT_TOOL_GEMINI_API_KEY=你的密钥

# 本地模型 — LM Studio 端口 1234 已预设
SCRIPT_TOOL_LOCAL_LLM_URL=http://localhost:1234/v1
SCRIPT_TOOL_LOCAL_LLM_API_KEY=not-needed
```

#### AI 助手的快捷功能

聊天面板预设了 4 个快捷操作按钮：

| 按钮 | 功能 |
|------|------|
| 中译英 | 将剧本内容翻译成英文 |
| 英译中 | 将英文内容翻译成中文 |
| 润色 | 优化文本表达，提升流畅度 |
| 摘要 | 用简洁语言总结内容 |

#### AI 助手的项目感知能力

AI 助手**自动读取当前项目的流水线数据**作为对话上下文，包括：
- 项目基本信息（名称、原著、作者、剧本类型）
- 各 Stage 完成状态
- 人物列表（姓名、角色定位、描述）
- 人物关系网络
- 主线与支线情节
- 场景结构列表
- 已生成的剧本内容（前 3000 字符预览）

这意味着你可以直接问 AI 助手：
- "主角在第 3 场戏里说了什么？"
- "帮我把第 2 集的场景列表翻译成英文"
- "女配角和男主角是什么关系？"
- "帮我润色 scene_005 的对白"

#### AI 助手密钥验证

切换模型时，系统会检查对应的环境变量是否已配置。如果未配置，聊天面板会显示错误提示，告诉你需要设置哪个环境变量。

---

### 三、完整 .env 配置示例

以下是一个同时配置了 DeepSeek（流水线）和 Claude（AI 助手）的完整示例：

```bash
# ═══ 流水线（用 DeepSeek） ═══
SCRIPT_TOOL_AI_PROVIDER=deepseek
SCRIPT_TOOL_AI_MODEL=deepseek-chat
SCRIPT_TOOL_DEEPSEEK_API_KEY=sk-你的deepseek密钥

# ═══ AI 助手（额外启用 Claude） ═══
SCRIPT_TOOL_ANTHROPIC_API_KEY=sk-ant-api03-你的claude密钥

# ═══ 可选 ═══
SCRIPT_TOOL_DATABASE_URL=sqlite:///C:/Users/lenovo/script_tool.db
```

这样配置后：
- **流水线**使用 DeepSeek 生成剧本（省钱）
- **AI 助手**可以在 DeepSeek 和 Claude 之间切换
- 如果想在 AI 助手中使用 GPT 聊天，再加一行 `SCRIPT_TOOL_OPENAI_API_KEY=...`

---

### 四、API Key 安全建议

1. **❌ 不要把 `.env` 提交到 Git**（已在 `.gitignore` 中排除）
2. **✅** 生产环境直接设置系统环境变量，不使用 `.env` 文件
3. **✅** 定期更换 API Key，尤其是在公共网络环境下使用时
4. **✅** 在 API 平台设置使用额度限制，防止意外超支

---

## 使用指南

### 快速上手（3 步）

1. **新建项目** → 填写项目名称、原著信息、选择剧本类型
2. **导入小说** → 上传 `.txt` / `.docx` / `.md` 文件，或直接粘贴文本（至少 3 章）
3. **一键生成** → 6 个阶段自动完成，生成剧本

### 一键生成 vs 分步生成

| 模式 | 特点 | 适用场景 |
|------|------|---------|
| 🚀 **一键生成** | 6 阶段全自动，一次完成 | 快速出稿、对 AI 结果有信心 |
| 📋 **分步生成** | 每阶段可暂停审查 | 需要精细控制、人物众多的长篇小说 |

分步生成模式下，以下阶段完成后会**自动暂停**供你审查：

| 暂停点 | 可审查内容 | 可做什么 |
|--------|-----------|---------|
| Stage 1 完成后 | 每章人物、地点、情节 | 检查是否有漏人或错认 |
| Stage 2 完成后 | 综合人物表、关系图 | 调整关系、修改角色定位 |
| Stage 3 完成后 | 剧本场景列表 | **拖拽编排场景、增删合并拆分** |

### 场景编排看板（Stage 3）

Stage 3 完成后会出现 📋 **编排场景** 链接，点击进入看板：

- **按集分组**：场景自动分集显示，每集一列
- **拖拽排序**：拖拽场景卡片调整顺序
- **编辑场景**：点击编辑按钮修改地点、时间、人物、摘要
- **拆分场景**：长场景可拆分为两场
- **合并场景**：选中两个场景合并为一个
- **新增场景**：在任意集末尾添加新场景
- **自动编号**：保存时自动重新编号（scene_001, scene_002…）
- **触发 Stage 4**：编排满意后，从看板直接开始生成场景内容

### 查看和导出结果

流水线完成后：

- 📝 **查看/编辑剧本** — 在线预览标准格式剧本，支持编辑保存
- ⬇ **下载 YAML** — 导出结构化 YAML 数据（机器可读，含完整元数据）
- ⬇ **下载 PDF** — 导出行业标准排版 PDF（Courier 12pt，适合打印/提交）

---

## 6 阶段流水线详解

```
Stage 0 → Stage 1 → Stage 2 → 🛑暂停 → Stage 3 → 🛑暂停 → Stage 4 → Stage 5
  5%       30%      10%                10%                40%        5%
```

### Stage 0 — 文本预处理（权重 5%）

- **输入**：原始小说文本
- **处理**：正则匹配章节标题（"第一章" / "Chapter 1" 等），自动拆分章节
- **输出**：`PreprocessResult`（标题、章节列表、总字数）
- **支持格式**：`.txt`、`.docx`（自动提取正文）、`.md`（自动转纯文本）
- **限制**：至少 3 章，最多 50 万字

### Stage 1 — 分章节分析（权重 30%）

- **输入**：Stage 0 输出的章节列表
- **处理**：N 个章节**并行**调用 AI，逐章提取人物、地点、情节、台词
- **输出**：`ChapterAnalysis[]`（每章的 new_characters、locations、plot_events、dialogue_excerpts）
- **进度**：实时显示 "章节分析 X/N"

### Stage 2 — 跨章节综合（权重 10%）🛑暂停点

- **输入**：Stage 1 输出的所有章节分析结果
- **处理**：AI 综合去重，合并同名人物、建立关系网络、梳理主线支线
- **输出**：`GlobalAnalysis`
  - `characters`：综合人物表（姓名、别名、定位、性格标签、首次出场章节）
  - `relationships`：人物关系网络（A → B，关系类型，描述）
  - `locations`：场景目录
  - `main_plot`：主线情节概述
  - `subplots`：支线列表

### Stage 3 — 剧本结构设计（权重 10%）🛑暂停点

- **输入**：Stage 2 输出的综合人物与情节分析
- **处理**：AI 设计场景列表，规划每场的地点、时间、出场人物、内容概要
- **输出**：`ScriptStructure`
  - `scenes`：场景计划列表（含 act/episode/sequence/location/characters/summary）
  - `episode_summaries`：集摘要（电视剧模式）
  - `beat_sheet`：节拍表（电影编剧术语）

### Stage 4 — 逐场内容生成（权重 40%）

- **输入**：Stage 3 输出的场景计划 + Stage 2 人物表 + Stage 0 原始章节文本
- **处理**：M 个场景**并行**调用 AI，生成完整的动作描写、对白、旁白、转场
- **输出**：`GeneratedScene[]`（标准剧本格式：scene_heading + content[]，含多类型内容元素）
- **容错**：空场景自动跳过，不中断流水线
- **进度**：实时显示 "场景生成 X/M"

### Stage 5 — 组装 & 校验（权重 5%）

- **输入**：所有前序阶段的输出
- **处理**：
  1. 构建标准人物表（含 id、name、role、traits）
  2. 组装 YAML 结构化输出（meta + config + characters + scenes）
  3. 转换为**行业标准中文剧本格式**（角色名对齐、场次标题、动作/对白/旁白分离）
- **输出**：`AssemblyResult`（yaml_text + screenplay_text + warnings）
- **校验**：检查必填字段完整性，输出警告信息

---

## 功能模块说明

### 文件导入模块（Stage 0 预处理）

| 格式 | 解析方式 | 说明 |
|------|---------|------|
| `.txt` | 正则拆分章节 | 中文（"第X章"）和英文（"Chapter X"）模式均支持 |
| `.docx` | python-docx 提取 | 自动提取所有段落文本，处理 Word 特殊格式 |
| `.md` | markdown 转纯文本 | 先转 HTML 再去除标签，保留纯文本内容 |
| 直接粘贴 | 同 `.txt` | 最长 50 万字限制，textarea 粘贴即可 |

### 缓存与断点续传

每阶段结果自动以 **input_hash** 为键缓存到 SQLite：
- 同一内容的同一阶段不重复调用 AI（节省时间和费用）
- 重置缓存后重新运行会重新生成
- 分步模式暂停期间，已完成阶段不受影响

### 安全机制

| 机制 | 说明 |
|------|------|
| 心跳检测 | SSE 连接 30 秒无响应自动断连 |
| 自动重试 | Stage 4 场景生成失败自动重试（最多 2 次） |
| 空场景跳过 | AI 返回空内容的场景自动过滤，带警告提示 |
| 速率限制 | 并发 AI 调用自动限流（asyncio.Semaphore） |

---

## API 接口文档

### 页面路由（Pages）

| 路由 | 说明 |
|------|------|
| `GET /` | 首页，项目列表 |
| `GET /projects/new` | 新建项目页面 |
| `GET /projects/{id}` | 项目工作台 |
| `GET /projects/{id}/stage/{n}` | Stage N 中间结果审查 |
| `GET /projects/{id}/stage3/kanban` | 场景编排看板 |
| `GET /projects/{id}/characters` | 人物关系图谱 |
| `GET /projects/{id}/script` | 在线剧本查看/编辑 |

### REST API

| 方法 | 路由 | 说明 |
|------|------|------|
| `POST` | `/api/projects` | 创建项目 |
| `POST` | `/api/projects/{id}/upload` | 上传小说文件 |
| `POST` | `/api/projects/{id}/paste` | 粘贴小说文本 |
| `GET` | `/api/projects/{id}/text` | 获取已保存的文本 |
| `POST` | `/api/projects/{id}/run` | **一键生成**（SSE 流式） |
| `POST` | `/api/projects/{id}/run-stage/{n}` | **分步生成**单阶段（SSE 流式） |
| `GET` | `/api/projects/{id}/stage/{n}` | 获取阶段缓存数据 |
| `PUT` | `/api/projects/{id}/stage/5` | 保存编辑后的剧本 |
| `POST` | `/api/projects/{id}/clear-cache` | 清除缓存（`?stage=N` 可选） |
| `DELETE` | `/api/projects/{id}` | 删除项目 |
| `GET` | `/api/projects/{id}/script.yaml` | 下载 YAML |
| `GET` | `/api/projects/{id}/script.pdf` | 下载 PDF |
| `GET` | `/api/projects/{id}/character-graph` | 人物关系图谱数据 |
| `GET` | `/api/projects/{id}/scenes` | 获取场景列表（看板用） |
| `PUT` | `/api/projects/{id}/scenes` | 保存场景列表（看板用） |
| `POST` | `/api/projects/{id}/scenes/split/{scene_id}` | 拆分场景 |
| `POST` | `/api/projects/{id}/scenes/merge` | 合并场景 |
| `POST` | `/api/projects/{id}/chat` | AI 助手聊天（SSE 流式） |

### SSE 事件格式

所有流式接口（`/run`、`/run-stage`、`/chat`）均使用以下格式：

```
data: {"message": "正在分析...", "percent": 15, "current_stage": 1, "stage_status": {...}}
data: {"status": "complete", "yaml_text": "...", "screenplay_text": "..."}
```

前端通过 `EventSource` / `fetch + ReadableStream` 消费事件流，实时更新进度条和阶段状态。

---

## 常见问题

### 启动与连接

**Q: 启动后浏览器打不开 http://localhost:8000？**

A: 检查以下项目：
1. 确认 Uvicorn 已正常启动（终端有 `Uvicorn running on http://0.0.0.0:8000` 提示）
2. 确认端口 8000 未被占用：`netstat -ano | findstr 8000`（Windows）/ `lsof -i :8000`（macOS/Linux）
3. 尝试换端口：`--port 8001`

**Q: WSL / Git Bash 启动报 `database is locked`？**

A: 这是跨文件系统 SQLite 锁问题，解决方案：
1. 在 `.env` 中设置 Windows 路径：`SCRIPT_TOOL_DATABASE_URL=sqlite:///C:/Users/你的用户名/script_tool.db`
2. 或使用 `start.sh` 启动，脚本会自动处理

### AI 配置

**Q: 一键生成报错 "API Key 无效"？**

A: 检查 `.env` 文件中的 API Key 是否正确：
- Claude：以 `sk-ant-api03-` 开头
- OpenAI：以 `sk-proj-` 或 `sk-` 开头
- DeepSeek：以 `sk-` 开头
- Gemini：无固定前缀

**Q: 本地模型（LM Studio）连接失败？**

A: 检查：
1. LM Studio → Developer 标签 → **Start Server** 是否已启动
2. 端口是否为 **1234**（默认不要改）
3. 模型名是否与 LM Studio 中加载的一致

**Q: 能不能流水线用 DeepSeek，AI 助手用 Claude？**

A: 完全可以。同时配置两者的 API Key：
```bash
SCRIPT_TOOL_AI_PROVIDER=deepseek
SCRIPT_TOOL_DEEPSEEK_API_KEY=sk-xxx
SCRIPT_TOOL_ANTHROPIC_API_KEY=sk-ant-api03-xxx
```
流水线使用 DeepSeek，AI 助手下拉菜单选择 Claude 即可。

### 剧本生成

**Q: 一次能处理多长的小说？**

A: 建议 20 章以内、50 万字以内。更长的小说可以：
1. 分成多个项目分批处理
2. 减少 Stage 3 的场景数（在看板中手动精简）

**Q: Stage 4 场景内容为空怎么办？**

A: 系统已内置自动跳过机制——空场景会被过滤并显示警告，不会中断流水线。如果大量场景为空：
1. 尝试换用其他 AI 模型
2. 在 Stage 3 看板中减少场景复杂度
3. 清除 Stage 4 缓存后重试

**Q: 生成过程很慢？**

A: Stage 1 和 Stage 4 是并行处理的，耗时取决于 AI API 响应速度和并发数。建议：
- 使用 DeepSeek 或本地模型（响应速度更快）
- 减少场景数（在 Stage 3 看板中精简）

### 数据

**Q: 数据存在哪里？**

A: 所有数据存储在 `storage/` 目录：
- `storage/db.sqlite` — SQLite 数据库（项目、缓存、运行记录）
- `storage/texts/` — 上传的文本文件
- 支持通过 `SCRIPT_TOOL_DATABASE_URL` 自定义数据库路径

**Q: 如何备份数据？**

A: 复制整个 `storage/` 目录即可，包含所有项目数据、缓存和文本文件。

---

## 开发指南

### 运行测试

```bash
pytest tests/ -v
# 35+ 测试用例，覆盖核心流水线和 API
```

### 代码规范

- Python 3.10+ 类型注解（`dataclass` 数据模型）
- FastAPI 依赖注入（`Depends(get_db)` 数据库会话）
- AI Provider 统一 `async` 接口（`generate` + `generate_stream`）
- 前端使用 HTMX + 原生 JavaScript（无框架依赖）

### 添加新的 AI Provider

1. 在 `app/ai/` 下创建新文件，继承 `AIProvider` 接口
2. 实现 `generate()`、`generate_stream()`、`model_name()` 三个方法
3. 在 `app/config.py` 添加对应的环境变量
4. 在 `app/ai/factory.py` 的 `create_ai_provider()` 中添加分支
5. 在 `app/routes/chat.py` 的 `PROVIDER_KEY_MAP` 中注册密钥检查

### 项目配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_UPLOAD_BYTES` | 10 MB | 文件上传大小限制 |
| `MAX_PASTE_CHARS` | 500,000 | 粘贴文本字数限制 |
| `DATABASE_URL` | 自动检测 | SQLite 数据库路径 |

---

## 许可证

MIT License
