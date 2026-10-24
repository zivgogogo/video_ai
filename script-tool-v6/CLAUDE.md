# CLAUDE.md

AI 辅助剧本创作工具 — 将小说文本自动转换为结构化 YAML 剧本。

## 启动

```bash
pip install -r requirements.txt

# 设置 AI API Key
export SCRIPT_TOOL_ANTHROPIC_API_KEY="sk-ant-..."

# WSL 环境注意：Windows Python 需设置 Windows 本机路径
export SCRIPT_TOOL_DATABASE_URL="sqlite:///C:/Users/15387/script_tool.db"

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 打开 http://localhost:8000
```

## 测试

```bash
pytest tests/ -v   # 35 tests
```

## 架构

- **Web**: FastAPI + Jinja2 SSR + HTMX
- **DB**: SQLite (SQLAlchemy)
- **AI**: Claude / GPT / 本地模型 (app/ai/)
- **流水线**: 6 阶段 (app/pipeline/executor.py):

```
Stage 0: 文本预处理 (章节拆分)
Stage 1: 分章节分析 (人物/地点/情节，可并行)
Stage 2: 跨章节综合 (去重、关系图)       ◀ 暂停点
Stage 3: 剧本结构设计 (场景列表)         ◀ 暂停点
Stage 4: 逐场内容生成 (动作/对白，可并行)
Stage 5: YAML 组装 & 校验
```

## 关键文件

| 文件 | 职责 |
|------|------|
| `app/main.py` | FastAPI 入口 |
| `app/models.py` | Project, PipelineRun, StageCache |
| `app/pipeline/executor.py` | 流水线调度 |
| `app/pipeline/stage5_assembly.py` | YAML 组装 |
| `app/ai/interface.py` | AIProvider 抽象接口 |
| `app/routes/api.py` | REST API + SSE |
| `docs/script-yaml-schema.md` | YAML Schema 规范 |

## 已知问题

- WSL 跨文件系统 SQLite 锁问题：需设置 `SCRIPT_TOOL_DATABASE_URL` 指向 Windows 本机路径
- 子代理在 WSL 路径下文件写入可能丢失：优先用 Write 工具直接写文件
