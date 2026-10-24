"""v5：分镜结构化专业要素词典 + 汇总（Prompt 中心用）。

要素与选项取自阿里云百炼「文生视频 Prompt 指南 / 提示词词典」+ 成熟短剧实践。
每个镜头用一个 elements 字典保存各要素取值；assemble_video_prompt /
assemble_image_prompt 把它们汇总成一段「标签头 + 小作文 + 负面约束」式 prompt
（即 shot.video_prompt / ai_image_prompt）。选项仅供前端下拉参考，汇总时不强制校验，
允许用户填自定义值或留空（留空的要素自动跳过）。
"""

# ── 选项类要素（前端渲染为下拉；multi=True 为多选）──────────────
ELEMENT_OPTIONS = {
    "shot_type":       {"label": "镜头类型", "options": [
        "干净的单人镜头", "双人镜头", "群像镜头", "定场镜头", "空镜", "过肩双人"]},
    "shot_size":       {"label": "景别", "options": [
        "大远景", "远景", "全景", "中全景", "中景", "中近景", "近景", "特写", "大特写"]},
    "camera_angle":    {"label": "机位角度", "options": [
        "平拍", "俯拍(高角度)", "仰拍(低角度)", "鸟瞰", "顶视", "过肩", "主观POV", "侧拍"]},
    "focal_length":    {"label": "焦段", "options": [
        "超广角-鱼眼", "广角", "标准35mm", "中焦距50mm", "中长焦", "长焦"]},
    "camera_movement": {"label": "运镜", "options": [
        "固定镜头", "推近", "拉远", "左移", "右移", "上摇", "下摇", "跟移",
        "环绕", "手持晃动", "升降", "复合运镜", "无人机航拍", "移轴", "延时"]},
    "composition":     {"label": "构图", "options": [
        "中心构图", "对称构图", "三分法", "左侧重", "右侧重", "平衡构图",
        "框架构图", "引导线", "前景遮挡", "短边构图"]},
    "time_of_day":     {"label": "时间段", "options": [
        "清晨", "白天", "正午", "黄昏", "日落", "夜晚", "黎明", "深夜"]},
    "light_source":    {"label": "光源", "options": [
        "日光", "晴天光", "阴天光", "黄金时刻", "蓝调时刻", "火光", "烛光",
        "实用光", "霓虹", "荧光", "混合光", "屏幕光", "月光"]},
    "lighting":        {"label": "光线", "multi": True, "options": [
        "柔光", "硬光", "侧光", "边缘光", "逆光", "顶光", "底光", "伦勃朗光"]},
    "color_tone":      {"label": "色调", "options": [
        "暖色调", "冷色调", "青橙", "黑白", "低饱和度", "高饱和度",
        "混合色调", "莫兰迪", "胶片色", "霓虹色"]},
    "contrast":        {"label": "对比度", "options": ["低对比度", "适中", "高对比度"]},
    "mood":            {"label": "氛围", "options": [
        "紧张", "悬疑", "温馨", "浪漫", "压抑", "欢快", "史诗", "苍凉",
        "诡异", "宁静", "热血", "悲伤", "暧昧"]},
    "emotion":         {"label": "角色情绪", "options": [
        "平静", "高兴", "悲伤", "愤怒", "惊讶", "恐惧", "深情", "犹豫",
        "冷漠", "激动", "羞涩"]},
    "visual_style":    {"label": "风格", "options": [
        "电影感写实", "纪录片", "黑色电影", "赛博朋克", "日系动漫", "国风水墨",
        "3D卡通", "黏土", "毛毡", "像素", "复古胶片", "梦幻超现实"]},
    "quality":         {"label": "画质", "multi": True, "options": [
        "电影级", "高清", "超清细节", "35mm胶片质感", "4K"]},
}

# ── 文本类要素（前端渲染为输入框/文本域）──────────────────────
TEXT_ELEMENTS = {
    "subject":     "主体/人物（外观锚定，避免'一名男子'等模糊指代）",
    "action":      "动作/表演（具体、可视化）",
    "dialogue":    "对话/台词（内心独白加〔内心〕、旁白加〔旁白〕前缀）",
    "scene":       "场景（地点/空间）",
    "environment": "环境（背景/前景/天气/陈设等细节）",
}

# 汇总时「标签头」里各选项要素的排列顺序（不含 mood/emotion，它们进正文）
TAG_ORDER = ["shot_type", "shot_size", "camera_angle", "focal_length",
             "camera_movement", "composition", "time_of_day", "light_source",
             "lighting", "color_tone", "contrast", "visual_style", "quality"]
# 静态图汇总不含运镜
TAG_ORDER_IMAGE = [k for k in TAG_ORDER if k != "camera_movement"]

NEGATIVE_RULES = ("画面中不得出现任何文字、字幕、水印、logo、边框；"
                  "避免肢体畸形、多余或缺失手指、面部扭曲、模糊、过曝、闪烁与抖动。")


def new_elements() -> dict:
    """返回一个空的 elements 骨架（多选项为 []，其余为 ''）。"""
    e = {}
    for k, v in ELEMENT_OPTIONS.items():
        e[k] = [] if v.get("multi") else ""
    for k in TEXT_ELEMENTS:
        e[k] = ""
    return e


def _vals(v) -> list:
    """要素值可能是 str 或 list（多选），统一成非空字符串列表。"""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v or "").strip()
    return [s] if s else []


def _one(elements: dict, key: str) -> str:
    """取单选要素的字符串值（多选则用顿号连接）。"""
    vs = _vals(elements.get(key))
    return "、".join(vs)


def _tag_header(elements: dict, order=None) -> str:
    """按顺序把选项要素拼成逗号分隔的标签头（去重、跳过空值）。"""
    order = order or TAG_ORDER
    tags = []
    for key in order:
        tags.extend(_vals(elements.get(key)))
    mood = _one(elements, "mood")
    if mood:
        tags.append(f"{mood}氛围")
    seen, out = set(), []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return "，".join(out)


def _dialogue_part(elements: dict) -> str:
    d = str(elements.get("dialogue") or "").strip()
    if not d:
        return ""
    if d.startswith("〔内心〕") or d.startswith("〔旁白〕") or d.startswith("〔"):
        return d
    return f"说：「{d}」"


def _body_sentence(elements: dict, with_dialogue: bool = True) -> str:
    subject = str(elements.get("subject") or "").strip()
    scene = str(elements.get("scene") or "").strip()
    env = str(elements.get("environment") or "").strip()
    action = str(elements.get("action") or "").strip()
    emotion = _one(elements, "emotion")

    segs = []
    loc = scene + (f"（{env}）" if env else "")
    if subject and loc:
        segs.append(f"{subject}在{loc}中")
    elif subject:
        segs.append(subject)
    elif loc:
        segs.append(loc)
    if action:
        segs.append(action)
    if emotion:
        segs.append(f"神情{emotion}")
    sentence = "，".join(segs)
    if with_dialogue:
        dlg = _dialogue_part(elements)
        if dlg:
            sentence = f"{sentence}，{dlg}" if sentence else dlg
    return sentence


def _join(head: str, body: str) -> str:
    parts = [p for p in (head, body) if p]
    s = "。".join(parts)
    if s and not s.endswith("。"):
        s += "。"
    return s


def assemble_video_prompt(elements: dict, beats: list = None) -> str:
    """汇总动态视频 prompt：标签头 + 正文 + 负面约束。

    beats 非空时，正文用「时间戳分段」（0-5秒：…；5-10秒：…），适配支持时序/
    多镜头描述的模型（如 Seedance 2.5、wan3.0 多镜头）；否则用整段小作文。
    """
    elements = elements or {}
    head = _tag_header(elements, TAG_ORDER)
    body = assemble_timeline_body(beats) or _body_sentence(elements, with_dialogue=True)
    return _join(head, body) + NEGATIVE_RULES


def assemble_image_prompt(elements: dict) -> str:
    """汇总静态图 prompt：标签头（不含运镜）+ 小作文（不含台词）+ 负面约束。"""
    elements = elements or {}
    head = _tag_header(elements, TAG_ORDER_IMAGE)
    body = _body_sentence(elements, with_dialogue=False)
    return _join(head, body) + NEGATIVE_RULES


# ── v6：画面时间轴（时间戳定向编辑）──────────────────────
# 每个 beat = 一段时间内的画面：{start, end, action, camera, dialogue}。
# 汇总成「0-5秒：…；5-10秒：…」式 prompt，喂给支持时序的模型；
# 不支持时序的模型也能把它当作更结构化的分段描述。

def new_beat() -> dict:
    """一个空的时间轴分段骨架。"""
    return {"start": 0.0, "end": 0.0, "action": "", "camera": "", "dialogue": ""}


def normalize_beats(beats, duration=None) -> list:
    """规整时间轴：过滤空段、数值化时间、按 start 排序、夹取到 [0, duration]。"""
    out = []
    for b in beats or []:
        if not isinstance(b, dict):
            continue
        action = str(b.get("action") or "").strip()
        camera = str(b.get("camera") or "").strip()
        dialogue = str(b.get("dialogue") or "").strip()
        if not (action or camera or dialogue):
            continue
        try:
            start = float(b.get("start") or 0)
        except (TypeError, ValueError):
            start = 0.0
        try:
            end = float(b.get("end") or 0)
        except (TypeError, ValueError):
            end = 0.0
        if end < start:
            start, end = end, start
        out.append({"start": round(max(0.0, start), 2),
                    "end": round(max(0.0, end), 2),
                    "action": action, "camera": camera, "dialogue": dialogue})
    out.sort(key=lambda x: (x["start"], x["end"]))
    try:
        d = float(duration) if duration else 0.0
    except (TypeError, ValueError):
        d = 0.0
    if d > 0:
        for b in out:
            b["start"] = round(min(b["start"], d), 2)
            b["end"] = round(min(max(b["end"], b["start"]), d), 2)
    return out


def assemble_timeline_body(beats) -> str:
    """把时间轴拼成正文：'0-5秒：动作（运镜）；5-10秒：…'。无有效段返回空串。"""
    beats = normalize_beats(beats)
    if not beats:
        return ""
    segs = []
    for b in beats:
        s, e = b["start"], b["end"]
        stamp = f"{s:g}-{e:g}秒" if e > s else f"{s:g}秒"
        body = b["action"]
        if b.get("camera"):
            body = f"{body}（{b['camera']}）" if body else f"（{b['camera']}）"
        if b.get("dialogue"):
            d = b["dialogue"]
            d = d if d.startswith("〔") else f"说：「{d}」"
            body = f"{body}，{d}" if body else d
        if body:
            segs.append(f"{stamp}：{body}")
    return "；".join(segs)
