# 8 个 UI/UX Bug 修复 — 修改文档

> 分支: `fix/upload-text-storage`  
> 日期: 2026-06-05  
> 关联: [[htmx-paste-button-bug]] [[project-overview]] [[openai-custom-base-url]]

---

## 修改概览

| # | Bug | 严重程度 | 改动文件 |
|---|-----|---------|---------|
| 1 | 解析文本按钮无反应 | 🔴 阻断 | `project.html` |
| 2 | 剧本只能看不能编辑 | 🔴 缺失功能 | `script_view.html`, `api.py`, `style.css` |
| 3 | 下载 YAML 为空白文件 | 🔴 阻断 | `api.py` |
| 4 | 缺少进度条 | 🟡 体验 | `project.html`, `api.py`, `style.css` |
| 5 | 上传文件无类型提示 | 🟢 提示 | `project.html` |
| 6 | 无删除项目功能 | 🟡 缺失功能 | `index.html`, `style.css` |
| 7 | 新建项目显示丑陋 JSON | 🟡 体验 | `api.py`, `style.css` |
| 8 | 测试步骤 | 📋 流程 | 本文档包含测试 checklist |

---

## Bug 1: 解析文本按钮无反应

**根因**: HTMX 2.0 移除了 `previous`/`next` CSS 选择器，`hx-include="previous textarea"` 找不到 textarea。

**修复**: `app/templates/project.html:13-14`
- 给 textarea 添加 `id="paste-text"`
- `hx-include` 改为 `hx-include="#paste-text"`

```html
<!-- 修复前 -->
<textarea name="text" placeholder="或直接粘贴小说文本..." ...></textarea>
<button hx-post="..." hx-include="previous textarea" ...>解析文本</button>

<!-- 修复后 -->
<textarea name="text" id="paste-text" placeholder="或直接粘贴小说文本..." ...></textarea>
<button hx-post="..." hx-include="#paste-text" ...>解析文本</button>
```

---

## Bug 2: 剧本编辑器（查看 → 编辑 → 保存）

**根因**: `script_view.html` 仅将 YAML 渲染到 `<pre>` 只读展示，无任何编辑能力。

**修复**: 三个文件联动

### 2a. 新增保存 API — `app/routes/api.py`
- `PUT /api/projects/{project_id}/stage/5` — 接收 `{"yaml_text": "..."}`
- 更新最新 stage 5 的 `StageCache.output_json` 中的 `yaml_text` 字段
- 无缓存时返回 404

### 2b. 重写剧本页面 — `app/templates/script_view.html`
```
操作流程（傻瓜用户友好）:

  只读模式: [代码块] + [✏️ 编辑剧本] [返回工作台]
       ↓ 点击 ✏️ 编辑剧本
  编辑模式: [可编辑 textarea] + [💾 保存修改] [❌ 取消编辑]
       ↓ 点击 💾 保存修改
       → 调用 PUT API → toast "✅ 修改已保存！" → 回到只读模式
       ↓ 点击 ❌ 取消编辑
       → 恢复原始内容 → 回到只读模式（不调用 API）
```

### 2c. 样式 — `static/css/style.css`
- textarea 编辑样式：等宽字体、白底黑字、蓝色边框

---

## Bug 3: YAML 下载空白文件

**根因**: `download_script` 接收 `yaml_text` 查询参数（默认空字符串），`downloadYAML()` JS 函数未传此参数 → 永远返回空字符串。

**修复**: `app/routes/api.py` — `download_script` 端点
- 移除 `yaml_text` 查询参数
- 改为从 `StageCache`（project_id + stage=5, 最新记录）读取 `output_json` → 提取 `yaml_text`
- 无缓存时返回 404: "剧本 YAML 尚未生成，请先运行流水线"

---

## Bug 4: 百分比进度条

**修复**: 三处联动

### 4a. 后端 SSE 添加 percent — `app/routes/api.py`
- 新增 `_inject_percent(msg)` 辅助函数
- 根据 `stage_status` 中 "done" 的 stage 数量计算百分比: `done_count * 100 // 6`
- 单步完成消息也支持 percent（`(stage + 1) * 100 // 6`）
- 在两个 SSE 循环中调用 `_inject_percent(msg)` before yield

### 4b. 前端进度条 UI — `app/templates/project.html`
- 新增 `<progress id="progress-bar" value="0" max="100">` + 百分比文字 `<span>`
- 默认隐藏，首次收到 percent 时显示
- 新增 `updateProgress(percent)` JS 函数
- 在 `runPipeline()` 和 `runNextStage()` 的 SSE handler 中调用 `updateProgress`

### 4c. 样式 — `static/css/style.css`
```css
progress { height: 20px; border-radius: 10px; ... }
progress::-webkit-progress-value { transition: width 0.3s ease; }
```

---

## Bug 5: 上传文件格式提示

**修复**: `app/templates/project.html:9` — `<input type="file">` 后添加：
```html
<small style="color:#6b7280">支持 .txt / .docx / .md 格式</small>
```

---

## Bug 6: 项目删除按钮

**修复**: 两处

### 6a. 首页卡片 — `app/templates/index.html`
每个 `.project-card` 添加红色删除按钮：
```html
<button class="btn-danger"
        hx-delete="/api/projects/{{ p.id }}"
        hx-confirm="确定要删除项目「{{ p.title }}」吗？此操作不可撤销。"
        hx-target="closest .project-card"
        hx-swap="delete">🗑 删除</button>
```

### 6b. 样式 — `static/css/style.css`
```css
.btn-danger { background: #ef4444; ... }
.btn-danger:hover { background: #dc2626; }
```

注：后端 API `DELETE /api/projects/{project_id}` 已存在，无需修改。

---

## Bug 7: 新建项目成功弹窗

**修复**: 两处

### 7a. API 双模式响应 — `app/routes/api.py` `create_project`
- 检测 `request.headers.get("HX-Request")`
  - **有 HX-Request**（浏览器 HTMX 请求）→ 返回 HTML 弹窗片段
  - **无 HX-Request**（curl/API 客户端）→ 返回 JSON（保持兼容）

### 7b. 弹窗内容
- 动态 GIF 表情包（CDN：Tenor peach-goma celebration GIF）
- 文案："项目「{title}」创建成功！🎉" + "「{title}」已就绪"
- 「前往项目工作台」链接 + 「✕ 关闭」按钮
- 3 秒自动淡出关闭
- CSS `@keyframes fadeIn` + `scaleIn` 入场动画

### 7c. 样式 — `static/css/style.css`
```css
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes scaleIn { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
```

---

## 涉及文件清单

| 文件 | 改动行数 | 涉及 Bug |
|------|---------|---------|
| `app/routes/api.py` | +98 / -2 | #2, #3, #4, #7 |
| `app/templates/project.html` | +23 / -1 | #1, #4, #5 |
| `app/templates/script_view.html` | +117 / -5 | #2 |
| `app/templates/index.html` | +6 | #6 |
| `static/css/style.css` | +33 | #4, #6, #7 |

---

## 测试 Checklist

### Bug 1 — 解析文本
- [ ] 粘贴文本（>100字）→ 点击「解析文本」→ 显示章节数和字数
- [ ] 空文本框点「解析文本」→ 有合理反馈

### Bug 2 — 剧本编辑
- [ ] 已完成项目中 → 查看剧本 → 看到 YAML 代码块 + 「✏️ 编辑剧本」
- [ ] 点击「✏️ 编辑剧本」→ 变为白色文本框 + 「💾 保存修改」「❌ 取消编辑」
- [ ] 修改内容 → 点「❌ 取消编辑」→ 恢复原内容
- [ ] 再次编辑 → 修改内容 → 「💾 保存修改」→ 绿色 toast ✅
- [ ] 刷新页面 → 显示修改后的内容
- [ ] 下载 YAML → 包含修改后的内容

### Bug 3 — YAML 下载
- [ ] 已完成项目 → 点击下载 → 文件有内容，非空白
- [ ] 未运行项目 → 下载 → 友好报错

### Bug 4 — 进度条
- [ ] 一键生成 → 蓝色进度条从 0% → 100%，完成后变绿
- [ ] 分步生成 → 每步完成后百分比递增

### Bug 5 — 格式提示
- [ ] 上传区域可见灰色提示「支持 .txt / .docx / .md 格式」

### Bug 6 — 删除项目
- [ ] 首页每张卡片有红色「🗑 删除」按钮
- [ ] 点击 → 弹出确认框
- [ ] 取消 → 不变 | 确认 → 卡片消失

### Bug 7 — 新建弹窗
- [ ] 新建项目 → 弹窗出现，有动态 GIF
- [ ] 3 秒自动关闭 | 点 ✕ 立即关闭
- [ ] 点「前往项目工作台」→ 跳转
- [ ] curl POST 创建 → 返回 JSON（非 HTML）

---

## PR 内容模板（测试通过后使用）

**标题**: `fix: 修复 8 个 UI/UX 问题 — 文本解析、剧本编辑、YAML下载、进度条等`

**内容**:
```
## 修复内容

本次 PR 修复了 8 个影响核心使用流程的 UI/UX 缺陷：

### 🔧 Bug 修复
1. **解析文本按钮无反应** — HTMX 2.0 `previous` 选择器兼容（#1）
2. **YAML 下载空白文件** — 改为从数据库读取而非依赖空 query param（#3）

### ✨ 新功能
3. **剧本编辑器** — 剧本页支持查看→编辑→保存完整流程，新增 PUT 保存接口（#2）
4. **百分比进度条** — 流水线生成过程显示可视化进度（#4）
5. **删除项目按钮** — 首页卡片新增删除功能（#6）
6. **新建项目成功弹窗** — 动态 GIF + 自动关闭 + 跳转链接，替代丑陋 JSON（#7）

### 📝 体验优化
7. **文件格式提示** — 上传区域显示 `.txt / .docx / .md` 提示（#5）
8. **测试步骤清单** — 提供完整的手动测试 checklist（#8）

## 修改文件

| 文件 | 说明 |
|------|------|
| `app/routes/api.py` | Bug 2/3/4/7: 新增 PUT 保存接口、修复下载、SSE 添加 percent、弹窗 HTML 响应 |
| `app/templates/project.html` | Bug 1/4/5: hx-include 修复、进度条 UI + JS、格式提示 |
| `app/templates/script_view.html` | Bug 2: 完整编辑器重写 |
| `app/templates/index.html` | Bug 6: 删除按钮 |
| `static/css/style.css` | Bug 4/6/7: 进度条、删除按钮、弹窗动画样式 |

## 测试

详见 `docs/bugfix-8-ui-ux-2026-06-05.md` 中的完整测试 checklist。
```
