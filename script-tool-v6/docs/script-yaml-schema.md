# 剧本 YAML Schema 规范文档

**版本**: 1.0.0
**最后更新**: 2026-06-05

## 文档目的

本文档定义了一种用于结构化剧本的 YAML Schema。它旨在作为 AI 辅助剧本创作工具的中间表示格式——既是 AI 生成的目标输出，也是作者编辑和打磨的工作格式。

本 Schema 解决的核心问题：**小说文本是非结构化的自然语言，剧本需要结构化呈现。** 传统的剧本格式（如好莱坞标准格式、Fountain）面向"排版和阅读"，而这个 Schema 面向"生成和分析"——它使得剧本可以被程序化处理、增量修改、跨类型复用。

## Schema 总览

```
meta          — 元数据（标题、作者、类型、版本）
config        — 生成配置（控制 AI 行为）
characters    — 人物表（ID、属性、关系）
scenes        — 场景列表（核心内容）
extensions    — 类型特定扩展
```

## 完整 Schema 定义

以下使用 YAML 注释标注每个字段的类型、必需性和含义。

```yaml
# ============================================================
# meta — 剧本元数据
# 描述"这个剧本是什么"，所有字段对所有剧本类型通用
# ============================================================
meta:
  # 剧本标题，必需
  title: "剑出华山"                          # string, required

  # 来源小说名称，可选（非改编创作可不填）
  source_novel: "笑傲江湖"                   # string, optional

  # 来源小说作者，可选
  source_author: "金庸"                      # string, optional

  # 剧本类型，必需
  # 枚举: film | tv_series | stage_play | animation | other
  script_type: tv_series                     # string, required

  # 版本号，遵循语义化版本，必需
  version: "0.1.0"                          # string, required

  # 创建日期，ISO 8601 格式，必需
  created_at: "2026-06-05"                   # string, required

  # 最后修改日期，ISO 8601 格式，可选
  revised_at: "2026-06-05"                   # string, optional

  # 语言代码，遵循 BCP 47，可选
  language: "zh-CN"                          # string, optional

  # 一句话描述，可选
  description: "改编自《笑傲江湖》第 3-6 章"  # string, optional

# ============================================================
# config — 生成配置
# 描述"怎么生成这个剧本"，控制 AI 流水线行为
# 修改 config 后重新生成，meta 不受影响
# ============================================================
config:
  # 目标集数（TV 适用），可选
  target_episodes: 40                        # int, optional

  # 单集时长目标（TV 适用），可选
  target_duration_per_episode: "45min"       # string, optional

  # 总时长目标（电影适用），可选
  target_duration: "120min"                  # string, optional

  # 风格关键词，会影响对话和动作描写的语调，可选
  style: "传统武侠"                           # string, optional

  # 自定义参数（自由扩展），可选
  custom: {}                                 # map, optional

# ============================================================
# characters — 人物表
# 剧本中出现的所有角色，以 ID 为唯一标识
# ============================================================
characters:
  - id: char_001                              # string, required, 全局唯一
    name: "令狐冲"                             # string, required
    aliases: ["令狐师兄", "冲哥"]              # string[], optional — 用于 AI 解析原文指代
    role: protagonist                         # string, optional — protagonist/antagonist/supporting/cameo
    description: "华山派大弟子，洒脱不羁"       # string, optional
    traits: ["豁达", "重情义", "嗜酒"]         # string[], optional — 性格标签
    relationships:                            # array, optional
      - to: char_002                          #   string — 对方角色 ID
        type: "师徒"                           #   string — 关系类型（父子/恋人/师徒/仇敌/...）
        description: "授业恩师，情同父子"       #   string — 关系描述
    first_appearance_scene: scene_001         # string, optional — 首次出场场景 ID
    notes: ""                                 # string, optional — 作者备注

  - id: char_002
    name: "岳不群"
    role: supporting
    description: "华山派掌门，人称君子剑"
    traits: ["深沉", "工于心计"]

# ============================================================
# scenes — 场景列表
# 剧本的核心内容。每个 scene 是一个独立的场景单元。
# 场景之间是扁平的（无嵌套），通过 act/episode/sequence 字段分组。
# ============================================================
scenes:
  # --- 场景条目 ---
  - id: scene_001                            # string, required, 全局唯一
    # 分组字段（均为 optional，根据 script_type 使用）
    act: 1                                    # int, optional — 第几幕（电影/舞台剧）
    episode: 1                                # int, optional — 第几集（电视剧）
    sequence: 1                               # int, optional — 第几场（更细粒度排序）

    # 场景设定
    setting:
      location: "华山派正气堂"                #   string, required — 地点名称
      time: "清晨"                             #   string, optional — 时间描述（早晨/深夜/1920年代/...）
      description: "大厅正中悬'剑气之争'匾额"  #   string, optional — 场景环境描述

    # 出场人物
    characters_present: [char_001, char_002]  # string[], optional — 本场出现的角色 ID 列表

    # 场景内容（数组，每个元素是一个内容块）
    content:                                   # array, required
      - type: action                          #   string — action | dialogue | transition | note
        text: "令狐冲步入正气堂，衣衫不整。"    #   string — 内容文本

      - type: dialogue
        character: char_002                   #   string — 说话者 ID
        text: "冲儿，你昨夜又去后山饮酒了？"    #   string — 台词
        direction: "语重心长，带着失望"         #   string, optional — 表演指示（对应传统剧本的括号内容）

      - type: action
        text: "令狐冲低头不语，手指无意识地摩挲着剑柄。"

      - type: dialogue
        character: char_001
        text: "师父，弟子知错。"
        direction: "语气诚恳，却藏不住眼底的笑意"

      - type: transition
        text: "CUT TO:"                       #   string — 转场指令

      - type: note
        text: "此处可以考虑加入闪回：令狐冲在思过崖独饮的画面"

    # 页码估算，可选
    page: 1                                    # int, optional

    # 作者备注，可选
    notes: ""                                  # string, optional


# ============================================================
# extensions — 类型特定扩展
# 不同剧本类型特有的结构数据。
# 解析器应能忽略不认识的扩展字段。
# ============================================================
extensions:
  # 电视剧扩展
  tv_series:
    episode_summaries:                        # array — 每集大纲
      - episode: 1
        title: "剑气之争"                      #   string, optional — 集标题
        summary: "令狐冲回山受罚，田伯光上山挑衅，风清扬暗中授剑"
        scenes: [scene_001, scene_002]        #   string[] — 本集包含的场景 ID
        cliffhanger: "风清扬现身，一剑指住田伯光咽喉"

  # 电影扩展
  film:
    beat_sheet:                               # array — Blake Snyder 节拍表
      - beat: "开场画面"
        scene: scene_001
        description: "华山派的日常"

  # 舞台剧扩展
  stage_play:
    stage_directions:                         # map — 舞台指示
      set_changes: 12
      intermission_after: scene_015

  # 预留：自定义扩展
  custom: {}                                  # map — 用户或工具自定义数据
```

## 内容元素类型说明

`content` 数组中的元素有四种类型：

| type | 含义 | 示例 | 对应传统剧本概念 |
|------|------|------|-----------------|
| `action` | 动作/场景描述 | "张三推门进来，环顾四周。" | Action line / 地口 |
| `dialogue` | 对白 | 包含 `character`, `text`, 可选 `direction` | Character cue + Dialogue + Parenthetical |
| `transition` | 转场 | "CUT TO:", "FADE OUT.", "黑场。" | Transition |
| `note` | 注释/提示 | 作者给AI或自己留的备注 | 不属于传统剧本，但创作中很有用 |

## 人物 ID 体系

所有人物引用使用 ID 而非名字，这是本 Schema 区别于纯文本剧本的关键设计：

```
原文："令狐冲步入大堂，岳不群冷冷看着他。"
                                  人物表可引用
解析后:  char_001 步入大堂              ↑
        char_002 冷冷看着他。           ↑
```

**好处**:
- 支持别名解析（"令狐师兄" / "冲哥" / "令狐冲" → 同一个 char_001）
- 台词归属清晰（统计某角色戏份/台词量）
- 人物关系图谱可自动可视化
- 重名角色可以通过 ID 区分

## 为什么是扁平场景列表而非嵌套结构？

传统剧本嵌套结构：
```yaml
# ❌ 嵌套结构 — 难以增量编辑
acts:
  - act: 1
    scenes:
      - scene: 1
        content: [...]
      - scene: 2
        content: [...]
  - act: 2
    scenes: [...]
```

本 Schema 的扁平结构：
```yaml
# ✅ 扁平结构 — 每个场景独立可编辑
scenes:
  - id: scene_001
    act: 1
    content: [...]
  - id: scene_002
    act: 1
    content: [...]
  - id: scene_003
    act: 2
    content: [...]
```

**设计原因**:

1. **AI 增量生成友好**: 流水线可以逐场生成/修改/替换，不需要操作深层嵌套结构
2. **顺序由序列号定义**: `act + episode + sequence` 三个可选字段组合，支持任意分组方式；改变分组不需要移动节点，改一个数字即可
3. **版本控制友好**: Git diff 在扁平结构上是清晰的单行变更；嵌套结构下插入一个场景会导致整个父节点 diff 混乱
4. **一致性**: 无论电影/电视剧/舞台剧，都是用同一组字段表达层次关系，只是字段的使用组合不同

## 为什么 content 是结构化数组而非纯文本？

```yaml
# ✅ 结构化
content:
  - type: dialogue
    character: char_001
    text: "我走了。"
    direction: "低声，眼里有泪"

# ❌ 纯文本
content: |
  令狐冲（低声，眼里有泪）
  我走了。
```

**设计原因**:

1. **可分析**: 可以统计每个角色的台词行数/字数，检测"某角色出场但无台词"等问题
2. **可程序化处理**: 导出不同格式（PDF/Fountain/HTML）时，每种元素类型有独立的渲染规则
3. **可增量编辑**: 修改一句台词只需要改一个数组元素，不需要操作整个文本块
4. **AI 生成精准**: LLM 可以逐个元素输出，结构化提示词比"生成一段剧本格式文本"更可控、输出更一致

**代价**: 手工编写时不如纯文本自然。这由一个带语法高亮的 Web 编辑器来弥补——作者看到的是类传统剧本的排版，实际存储是结构化 YAML。

## 为什么 extensions 独立于核心字段？

**设计原因**:

1. **核心 Schema 保持简洁**: `meta` + `config` + `characters` + `scenes` 是所有剧本类型的最大公约数，不加任何类型特定字段
2. **解析器兼容性**: 一个只理解电影格式的解析器可以安全忽略 `extensions.tv_series`，不会因为遇到未知字段而报错
3. **渐进增强**: 后续可以添加新扩展（如 `extensions.animation.storyboard_refs`）而不影响现有工具和现有数据

## Schema 版本兼容性

本 Schema 遵循语义化版本：

- **主版本 (1.x.x)**: 移除字段或改变字段语义，不保证向后兼容
- **次版本 (x.1.x)**: 新增字段，向后兼容（旧数据仍可解析）
- **修订版本 (x.x.1)**: 文档修正，不影响兼容性

当前版本 1.0.0 是初始稳定版本。实际项目中，建议在 `meta.version` 中标注目标 Schema 版本，解析器据此做兼容处理。

## 完整示例

完整示例已内嵌于上述 Schema 定义中（以《笑傲江湖》改编为例）。独立的示例文件将在项目实施时创建于 `examples/` 目录下。
