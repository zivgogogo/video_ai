import re
from dataclasses import dataclass, field
from docx import Document

@dataclass
class Chapter:
    index: int
    title: str
    content: str
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.content)

@dataclass
class PreprocessResult:
    title: str = ""
    chapters: list = field(default_factory=list)
    total_chars: int = 0
    errors: list = field(default_factory=list)

    def is_valid(self, min_chapters: int = 1) -> bool:
        """章节数不设下限：单章短篇同样可以走完整流水线。"""
        return len(self.chapters) >= min_chapters and self.total_chars > 0


def preprocess_text(text: str) -> PreprocessResult:
    result = PreprocessResult()
    if not text.strip():
        result.errors.append("输入文本为空")
        return result

    result.title = _extract_title(text)
    chapters = _split_chapters(text)
    result.chapters = [Chapter(index=i, title=t, content=c)
                       for i, (t, c) in enumerate(chapters)]
    result.total_chars = sum(c.char_count for c in result.chapters)
    return result


def preprocess_docx(file_bytes: bytes) -> PreprocessResult:
    try:
        from io import BytesIO
        doc = Document(BytesIO(file_bytes))
        text = "\n".join(p.text for p in doc.paragraphs)
        return preprocess_text(text)
    except Exception as e:
        result = PreprocessResult()
        result.errors.append(f"docx 解析失败: {e}")
        return result


def preprocess_markdown(text: str) -> PreprocessResult:
    import markdown
    html = markdown.markdown(text)
    plain = re.sub(r'<[^>]+>', '', html)
    return preprocess_text(plain)


def _extract_title(text: str) -> str:
    first_line = text.strip().split("\n")[0].strip()
    first_line = re.sub(r'^[#\s]+', '', first_line)
    return first_line[:100] if len(first_line) <= 100 else first_line[:97] + "..."


def _split_chapters(text: str) -> list:
    patterns = [
        r'(?:^|\n)\s*(?:第[一二三四五六七八九十百千\d]+[章节回部卷])[：:\s]*[^\n]{0,50}',
        r'(?:^|\n)\s*(?:Chapter|CHAPTER|ch)\s*\d+[：:\s]*[^\n]{0,50}',
    ]
    for pattern in patterns:
        parts = re.split(pattern, text, flags=re.MULTILINE)
        titles = re.findall(pattern, text, flags=re.MULTILINE)
        if len(parts) > 1 and len(titles) >= 2:
            if parts[0].strip() and len(parts[0].strip().split('\n')) >= 3:
                titles.insert(0, "序言/前言")
            else:
                parts = parts[1:]
            return [(titles[i].strip(), parts[i].strip()) if i < len(titles)
                    else (f"第{i+1}章", parts[i].strip())
                    for i in range(len(parts))]

    chunks = _fallback_split(text, 3000)
    return [(f"第{i+1}节", chunk) for i, chunk in enumerate(chunks)]


def _fallback_split(text: str, chunk_size: int) -> list:
    paragraphs = text.split('\n\n')
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) > chunk_size and current:
            chunks.append(current.strip())
            current = p
        else:
            current += "\n\n" + p if current else p
    if current.strip():
        chunks.append(current.strip())
    return chunks if len(chunks) >= 3 else [text]
