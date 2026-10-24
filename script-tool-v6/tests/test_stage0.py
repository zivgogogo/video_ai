import pytest
from app.pipeline.stage0_preprocess import preprocess_text, preprocess_markdown

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

@pytest.mark.parametrize("text", [
    "一段没有章节标题的独立正文。",
    "标题\n\n第一段正文。\n\n第二段正文。",
    "只有一行内容。",
])
def test_preprocess_single_chapter_is_valid(text):
    result = preprocess_text(text)
    assert len(result.chapters) == 1
    assert result.is_valid()

def test_preprocess_markdown():
    md = "# 剑出华山\n\n## 第一章\n\n令狐冲站在山巅。\n\n## 第二章\n\n思过崖上。\n\n## 第三章\n\n田伯光上山。"
    result = preprocess_markdown(md)
    assert len(result.chapters) >= 3

def test_preprocess_fallback_split():
    text = "\n\n".join([f"段落{i} " * 500 for i in range(10)])
    result = preprocess_text(text)
    assert len(result.chapters) >= 3
