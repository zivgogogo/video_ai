"""v4：独立「创作工作台」素材库存储（全局，不绑定具体小说项目）。

结构与 media_store 类似，但没有 project 维度：所有产物统一放在
WORKBENCH_DIR 下（items.json 记录元数据，images/ 与 videos/ 存文件）。
"""
import json
from app.config import WORKBENCH_DIR


def ensure_dirs():
    """确保工作台根目录与 images/videos 子目录存在。"""
    (WORKBENCH_DIR / "images").mkdir(parents=True, exist_ok=True)
    (WORKBENCH_DIR / "videos").mkdir(parents=True, exist_ok=True)
    return WORKBENCH_DIR


def _items_path():
    ensure_dirs()
    return WORKBENCH_DIR / "items.json"


def load_items() -> list:
    p = _items_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_items(items: list):
    _items_path().write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def image_path(filename: str):
    ensure_dirs()
    return WORKBENCH_DIR / "images" / filename


def video_path(filename: str):
    ensure_dirs()
    return WORKBENCH_DIR / "videos" / filename


def find_item(items: list, item_id: str):
    """按 id 定位 item，找不到返回 None。"""
    for it in items:
        if it.get("id") == item_id:
            return it
    return None
