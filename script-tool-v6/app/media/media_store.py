"""v3：项目媒体产物存储（角色档案 / 分镜 / 图片 / 视频）。"""
import json
from app.config import MEDIA_DIR


def project_dir(project_id: str):
    d = MEDIA_DIR / project_id
    (d / "images").mkdir(parents=True, exist_ok=True)
    (d / "videos").mkdir(parents=True, exist_ok=True)
    (d / "audio").mkdir(parents=True, exist_ok=True)   # v6：角色配音片段
    return d


def _load(path) -> list:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def load_characters(project_id: str) -> list:
    return _load(project_dir(project_id) / "characters.json")


def save_characters(project_id: str, chars: list):
    _save(project_dir(project_id) / "characters.json", chars)


def load_storyboard(project_id: str) -> list:
    return _load(project_dir(project_id) / "storyboard.json")


def save_storyboard(project_id: str, shots: list):
    _save(project_dir(project_id) / "storyboard.json", shots)


def load_videos(project_id: str) -> list:
    return _load(project_dir(project_id) / "videos.json")


def save_videos(project_id: str, videos: list):
    _save(project_dir(project_id) / "videos.json", videos)


def load_scene_refs(project_id: str) -> dict:
    """场景参考图：{scene_index(str): {file,url,prompt,created_at}}，用于锁定场景一致性。"""
    p = project_dir(project_id) / "scene_refs.json"
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_scene_refs(project_id: str, refs: dict):
    _save(project_dir(project_id) / "scene_refs.json", refs)


def image_path(project_id: str, filename: str):
    return project_dir(project_id) / "images" / filename


def video_path(project_id: str, filename: str):
    return project_dir(project_id) / "videos" / filename


def audio_path(project_id: str, filename: str):
    """v6：配音音频片段路径（media/{project_id}/audio/）。"""
    return project_dir(project_id) / "audio" / filename
