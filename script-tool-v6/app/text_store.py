"""项目文本 / 章节结构存储（v2：支持多文件导入的章节结构直接复用）。"""
import json
from app.config import TEXT_STORE_DIR


def text_path(project_id: str):
    return TEXT_STORE_DIR / f"{project_id}.txt"


def save_text(project_id: str, text: str):
    text_path(project_id).write_text(text, encoding="utf-8")


def load_text(project_id: str) -> str:
    p = text_path(project_id)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def chapters_path(project_id: str):
    return TEXT_STORE_DIR / f"{project_id}.chapters.json"


def save_chapters(project_id: str, chapters: list):
    """chapters: [{"index", "title", "content", "char_count"}]"""
    chapters_path(project_id).write_text(
        json.dumps(chapters, ensure_ascii=False), encoding="utf-8")


def load_chapters(project_id: str) -> list:
    p = chapters_path(project_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def clear_chapters(project_id: str):
    p = chapters_path(project_id)
    if p.exists():
        p.unlink()
