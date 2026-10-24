"""分镜生成（storyboard）升级的单元测试：场景内容渲染 / 模板格式化 / 场景头切分。"""
import re

from app.media import storyboard as sb


def test_render_scene_content_types():
    content = [
        {"type": "action", "text": "推门而入"},
        {"type": "dialogue", "character": "苏青鱼", "direction": "冷淡", "text": "我要冥币"},
        {"type": "dialogue", "character": "老板", "text": "好嘞"},
        {"type": "inner_monologue", "character": "苏青鱼", "text": "他不对劲"},
        {"type": "narration", "text": "夜色渐深"},
        {"type": "transition", "text": "CUT TO"},
        {"type": "action", "text": ""},   # 空文本应跳过
    ]
    out = sb._render_scene_content(content)
    assert "【动作/环境】推门而入" in out
    assert "苏青鱼（冷淡）：「我要冥币」" in out
    assert "老板：「好嘞」" in out
    assert "苏青鱼〔内心独白〕：他不对劲" in out
    assert "〔旁白〕夜色渐深" in out
    assert "〔转场〕CUT TO" in out
    # 空 action 不应产生孤立的标签行
    assert out.count("【动作/环境】") == 1


def test_render_scene_content_empty():
    assert sb._render_scene_content([]) == ""
    assert sb._render_scene_content(None) == ""


def test_prompt_template_formats():
    p = sb.STORYBOARD_PROMPT.format(
        shots=4, scene_title="白事店", scene_heading="[内景：白事店，夜]",
        location="白事店", time="夜", setting="昏黄", characters="苏青鱼、老板",
        appearances="- 苏青鱼：黑发年轻女子", scene_text="苏青鱼推门而入",
        style=sb.STYLE_ANCHOR, options_menu=sb._options_menu())
    assert "白事店" in p
    assert "- 苏青鱼：黑发年轻女子" in p          # 角色外观锚定注入
    assert "35mm" in p                             # 风格锚注入
    assert "elements" in p                         # 结构化输出指令
    assert "景别" in p                              # 专业要素候选菜单注入
    assert "禁止用" in p                            # 反模糊指代指令
    assert '"shots"' in p                          # JSON 结构示例


def test_stage5_scene_heading_split():
    text5 = "[内景：店，夜]\n内容A\n[外景：街，日]\n内容B\n[内景：屋，晨]\n内容C"
    chunks = [c for c in re.split(r"\n(?=\s*\[(?:内景|外景|内|外))", text5) if c.strip()]
    assert len(chunks) == 3
    assert chunks[0].startswith("[内景")
    assert chunks[1].startswith("[外景")
    assert chunks[2].startswith("[内景：屋")


def test_module_constants():
    assert sb.MAX_CONCURRENCY >= 1
    assert sb.STYLE_ANCHOR and sb.STORYBOARD_SYSTEM
    # 负面约束已迁至 prompt_elements，汇总时自动追加
    from app.media import prompt_elements as pe
    assert pe.NEGATIVE_RULES


def test_normalize_shot_structured():
    raw = {"shot_number": 1, "characters_present": ["苏青鱼"], "duration_seconds": 10,
           "elements": {"subject": "苏青鱼（黑发年轻女子）", "shot_size": "近景",
                        "dialogue": "我要冥币", "mood": "诡异", "scene": "白事店"}}
    shot = sb._normalize_shot(raw, scene_index=2, scene_title="白事店")
    assert shot["scene_index"] == 2
    assert shot["duration_seconds"] == 10
    assert shot["elements"]["shot_size"] == "近景"
    assert shot["elements"]["visual_style"] == "电影感写实"   # 风格兜底
    assert shot["elements"]["quality"] == ["电影级", "高清"]   # 画质兜底
    assert shot["dialogue"] == "我要冥币"                     # 顶层兼容字段同步
    assert "近景" in shot["video_prompt"]
    assert "说：「我要冥币」" in shot["video_prompt"]
    assert shot["ai_image_prompt"]                            # 静态图汇总也生成
