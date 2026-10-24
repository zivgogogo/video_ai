import yaml
from dataclasses import dataclass, field
from app.pipeline.stage2_cross_chapter_synthesis import GlobalAnalysis
from app.pipeline.stage3_script_structure import ScriptStructure
from app.pipeline.stage4_scene_generation import GeneratedScene

@dataclass
class AssemblyResult:
    yaml_text: str = ""
    screenplay_text: str = ""
    warnings: list = field(default_factory=list)
    is_valid: bool = False


def assemble(meta: dict, config: dict, global_analysis: GlobalAnalysis,
             structure: ScriptStructure, scenes: list) -> AssemblyResult:
    result = AssemblyResult()

    characters = _build_characters(global_analysis)
    name_to_id = {c["name"]: c["id"] for c in characters}
    # 也支持别名查找
    for c in characters:
        for alias in c.get("aliases", []):
            name_to_id[alias] = c["id"]

    # YAML 结构化输出（机器可读，保留向后兼容）
    script = {
        "meta": meta,
        "config": config,
        "characters": characters,
        "scenes": _build_scenes(scenes, name_to_id),
        "extensions": _build_extensions(config.get("script_type", "other"), structure),
    }

    result.yaml_text = yaml.dump(script, allow_unicode=True, default_flow_style=False,
                                  sort_keys=False, width=120)

    # 纯中文剧本格式输出（人类可读，符合行业标准）
    result.screenplay_text = format_full_screenplay(meta, global_analysis, scenes)

    result.warnings = _validate(script)
    result.is_valid = len([w for w in result.warnings if w.startswith("ERROR")]) == 0
    return result


def format_full_screenplay(meta: dict, global_analysis: GlobalAnalysis,
                           scenes: list) -> str:
    """将整个剧本渲染为纯中文标准剧本格式文本。

    输出格式参照中国电视剧标准剧本格式规范 (docs/chinese-screenplay-format.md)：
    - 标题：《xxx》
    - 人物表
    - 第X幕（第X-X集）
    - [场景标题]
    - 【动作描述】
    - 角色名： （表情提示）台词
    - 旁白（声音描述）： 内容
    - 角色名（内心独白）： 内容
    - [转换场景：...]
    - 剧终
    """
    lines = []

    # 构建角色名 → 信息的映射
    char_info = {c.get("name", ""): c for c in global_analysis.characters}

    # ── 标题 ──
    title = meta.get("title", "未命名")
    lines.append(f"标题：《{title}》")
    lines.append("")

    # ── 人物表 ──
    if global_analysis.characters:
        lines.append("人物表：")
        lines.append("")
        for c in global_analysis.characters:
            name = c.get("name", "")
            role = c.get("role", "")
            role_label = _role_label(role)
            desc = c.get("description", "")
            traits = "、".join(c.get("traits", []))
            line = f"{name} —— {role_label}"
            if desc:
                line += f"，{desc}"
            if traits:
                line += f"，性格：{traits}"
            lines.append(line)
        lines.append("")

    # ── 按幕分组场景 ──
    acts = _group_scenes_by_act(scenes)

    for act_num, act_scenes in acts.items():
        # 确定该幕的集数范围
        episodes = sorted(set(s.episode for s in act_scenes))
        if len(episodes) == 1:
            ep_range = f"第{episodes[0]}集"
        else:
            ep_range = f"第{episodes[0]}-{episodes[-1]}集"

        lines.append(f"第{_num_to_chinese(act_num)}幕（{ep_range}）")
        lines.append("")

        for scene in act_scenes:
            # 场景标题
            if scene.scene_heading:
                lines.append(scene.scene_heading)
                lines.append("")

            # 场景内容
            for elem in scene.content:
                typ = elem.get("type", "")
                text = elem.get("text", "")

                if typ == "action":
                    lines.append(f"【{text}】")

                elif typ == "dialogue":
                    char_name = elem.get("character", "")
                    direction = elem.get("direction", "")
                    if direction:
                        lines.append(f"{char_name}： （{direction}）{text}")
                    else:
                        lines.append(f"{char_name}： {text}")

                elif typ == "narration":
                    direction = elem.get("direction", "")
                    if direction:
                        lines.append(f"旁白（{direction}）： {text}")
                    else:
                        lines.append(f"旁白： {text}")

                elif typ == "inner_monologue":
                    char_name = elem.get("character", "")
                    lines.append(f"{char_name}（内心独白）： {text}")

                elif typ == "transition":
                    if text.startswith("[") or text.startswith("CUT"):
                        lines.append(text)
                    else:
                        lines.append(f"[转换场景：{text}]")

                elif typ == "note":
                    lines.append(f"（备注：{text}）")

                lines.append("")

            # 场景之间加空行分隔
            lines.append("")

    # ── 剧终 ──
    lines.append("剧终")

    return "\n".join(lines)


# ── 内部辅助函数 ──────────────────────────────────────────────────────


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


def _build_scenes(generated_scenes: list, name_to_id: dict) -> list:
    # 反向映射：ID → 角色名，用于格式化时显示角色名
    id_to_name = {v: k for k, v in name_to_id.items()}

    scenes = []
    for gs in generated_scenes:
        # 将 characters_present 中的角色名映射为 ID
        char_present_ids = [
            name_to_id.get(n, n) for n in gs.characters_present
        ]

        # 将 dialogue/inner_monologue 中的 character 角色名映射为 ID
        content = []
        for elem in gs.content:
            new_elem = dict(elem)
            if new_elem.get("character"):
                mapped = name_to_id.get(new_elem["character"])
                if mapped:
                    new_elem["character"] = mapped
            content.append(new_elem)

        scene = {
            "id": gs.id,
            "act": gs.act,
            "episode": gs.episode,
            "sequence": gs.sequence,
            "scene_heading": gs.scene_heading,
            "setting": {
                "location": gs.location,
                "time": gs.time,
                "description": gs.setting_description,
            },
            "characters_present": char_present_ids,
            "content": content,
            "scene_text": _format_scene_content(gs.scene_heading, content, id_to_name),
            "page": None,
            "notes": "",
        }
        scenes.append(scene)
    return scenes


def _format_scene_content(scene_heading: str, content: list, id_to_name: dict) -> str:
    """将结构化 content 数组渲染为中国电视剧标准剧本格式文本（单场）。"""
    lines = []

    # 场景标题
    if scene_heading:
        lines.append(scene_heading)
        lines.append("")

    for elem in content:
        typ = elem.get("type", "")
        text = elem.get("text", "")

        if typ == "action":
            lines.append(f"【{text}】")

        elif typ == "dialogue":
            char_id = elem.get("character", "")
            char_name = id_to_name.get(char_id, char_id)
            direction = elem.get("direction", "")
            if direction:
                lines.append(f"{char_name}： （{direction}）{text}")
            else:
                lines.append(f"{char_name}： {text}")

        elif typ == "narration":
            direction = elem.get("direction", "")
            if direction:
                lines.append(f"旁白（{direction}）： {text}")
            else:
                lines.append(f"旁白： {text}")

        elif typ == "inner_monologue":
            char_id = elem.get("character", "")
            char_name = id_to_name.get(char_id, char_id)
            lines.append(f"{char_name}（内心独白）： {text}")

        elif typ == "transition":
            if text.startswith("[") or text.startswith("CUT"):
                lines.append(text)
            else:
                lines.append(f"[转换场景：{text}]")

        elif typ == "note":
            lines.append(f"（备注：{text}）")

        lines.append("")

    return "\n".join(lines).strip()


def _group_scenes_by_act(scenes: list) -> dict:
    """将场景列表按幕（act）分组，保持原有顺序。"""
    acts = {}
    for s in scenes:
        act = getattr(s, 'act', 1)
        if act not in acts:
            acts[act] = []
        acts[act].append(s)
    return acts


def _num_to_chinese(n: int) -> str:
    """数字转中文（1-99）。"""
    digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    if n < 10:
        return digits[n]
    elif n < 20:
        return "十" + (digits[n % 10] if n % 10 != 0 else "")
    else:
        tens = n // 10
        ones = n % 10
        return digits[tens] + "十" + (digits[ones] if ones != 0 else "")


def _role_label(role: str) -> str:
    """角色类型 → 中文标签。"""
    labels = {
        "protagonist": "主角",
        "antagonist": "反派",
        "supporting": "配角",
        "minor": "次要角色",
        "cameo": "客串",
    }
    return labels.get(role, "配角")


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
            elem_type = elem.get("type", "")
            if elem_type in ("dialogue", "inner_monologue"):
                char_name = elem.get("character", "")
                if char_name and char_name not in char_ids:
                    warnings.append(f"WARNING: {scene['id']} 中 {elem_type} 归属未知角色 '{char_name}'")
    return warnings
