"""v5 结构化要素词典与汇总（prompt_elements）单元测试。"""
from app.media import prompt_elements as pe


def test_new_elements_skeleton():
    e = pe.new_elements()
    assert e["lighting"] == [] and e["quality"] == []     # 多选为列表
    assert e["shot_size"] == "" and e["subject"] == ""    # 单选/文本为空串
    # 所有选项要素与文本要素都在骨架里
    for k in pe.ELEMENT_OPTIONS:
        assert k in e
    for k in pe.TEXT_ELEMENTS:
        assert k in e


def test_assemble_video_full():
    e = pe.new_elements()
    e.update({
        "shot_type": "双人镜头", "shot_size": "中景", "camera_movement": "推近",
        "mood": "紧张", "lighting": ["柔光", "侧光"], "color_tone": "冷色调",
        "subject": "李寻欢（玄色长袍）", "scene": "客栈大堂", "environment": "烛影摇红",
        "action": "缓缓抬头", "emotion": "犹豫", "dialogue": "你终于来了",
        "visual_style": "电影感写实", "quality": ["电影级"],
    })
    p = pe.assemble_video_prompt(e)
    assert "双人镜头" in p and "中景" in p and "推近" in p
    assert "柔光，侧光" in p                                   # 多选→逗号分隔标签
    assert "紧张氛围" in p
    assert "李寻欢（玄色长袍）在客栈大堂（烛影摇红）中" in p
    assert "神情犹豫" in p
    assert "说：「你终于来了」" in p
    assert p.endswith(pe.NEGATIVE_RULES)


def test_assemble_image_excludes_movement_and_dialogue():
    e = pe.new_elements()
    e.update({"camera_movement": "环绕", "dialogue": "台词X",
              "subject": "人物", "shot_size": "近景"})
    im = pe.assemble_image_prompt(e)
    assert "环绕" not in im          # 静态图不含运镜
    assert "台词X" not in im         # 静态图不含台词
    assert "近景" in im and "人物" in im


def test_inner_monologue_prefix_kept():
    e = pe.new_elements()
    e["dialogue"] = "〔内心〕我不能退"
    p = pe.assemble_video_prompt(e)
    assert "〔内心〕我不能退" in p
    assert "「" not in p             # 带〔前缀的不再套「」


def test_empty_elements_only_negative():
    assert pe.assemble_video_prompt({}) == pe.NEGATIVE_RULES
    assert pe.assemble_video_prompt(pe.new_elements()) == pe.NEGATIVE_RULES


def test_tag_header_dedup_and_skip_empty():
    e = pe.new_elements()
    e["shot_size"] = "中景"
    e["color_tone"] = ""
    e["lighting"] = ["柔光", "柔光"]
    h = pe._tag_header(e)
    assert h.count("柔光") == 1      # 去重
    assert "中景" in h


def test_custom_value_passthrough():
    # 允许用户填词典之外的自定义值
    e = pe.new_elements()
    e["visual_style"] = "自定义水墨赛博"
    assert "自定义水墨赛博" in pe.assemble_video_prompt(e)
