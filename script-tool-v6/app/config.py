import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
# v4 起数据目录可指向别处（用于多版本共用同一份项目数据），默认仍为本目录 storage
_sd = os.getenv("SCRIPT_TOOL_STORAGE_DIR", "").strip()
STORAGE_DIR = Path(_sd) if _sd else BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
CACHE_DIR = STORAGE_DIR / "cache"
TEXT_STORE_DIR = STORAGE_DIR / "texts"
# 跨文件系统检测：代码在 WSL 路径但 Python 在 Windows 上运行时，
# SQLite 无法在 UNC 路径上加锁，自动重定向到 Windows 本机路径
_storage_path = str(STORAGE_DIR / "db.sqlite")
if _storage_path.startswith(r"\\wsl.localhost") or _storage_path.startswith("//wsl.localhost"):
    _win_user = os.environ.get("USERNAME", "default")
    DATABASE_URL = os.getenv("SCRIPT_TOOL_DATABASE_URL", f"sqlite:///C:/Users/{_win_user}/script_tool.db")
else:
    DATABASE_URL = os.getenv("SCRIPT_TOOL_DATABASE_URL", f"sqlite:///{STORAGE_DIR / 'db.sqlite'}")

AI_PROVIDER = os.getenv("SCRIPT_TOOL_AI_PROVIDER", "claude")
AI_MODEL = os.getenv("SCRIPT_TOOL_AI_MODEL", "claude-sonnet-4-6")
# 顶尖模型池（逗号分隔）：流水线各阶段轮转使用，失败时自动切换到池中下一个模型
MODEL_POOL = [m.strip() for m in os.getenv("SCRIPT_TOOL_MODEL_POOL", "").split(",") if m.strip()]
ANTHROPIC_API_KEY = os.getenv("SCRIPT_TOOL_ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("SCRIPT_TOOL_OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("SCRIPT_TOOL_OPENAI_BASE_URL")
DEEPSEEK_API_KEY = os.getenv("SCRIPT_TOOL_DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("SCRIPT_TOOL_DEEPSEEK_MODEL", "deepseek-chat")
GEMINI_API_KEY = os.getenv("SCRIPT_TOOL_GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("SCRIPT_TOOL_GEMINI_MODEL", "gemini-2.5-flash")
LOCAL_LLM_URL = os.getenv("SCRIPT_TOOL_LOCAL_LLM_URL", "http://localhost:1234/v1")
LOCAL_LLM_API_KEY = os.getenv("SCRIPT_TOOL_LOCAL_LLM_API_KEY", "not-needed")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PASTE_CHARS = 500_000

# ── v3：影视化媒体生成（文生角色图 / 分镜 / 视频）─────────────
MEDIA_DIR = STORAGE_DIR / "media"
# v4：独立「创作工作台」素材库（不绑定具体小说项目，全局共享）
WORKBENCH_DIR = STORAGE_DIR / "workbench"
# 导出/另存基础目录：默认在 v4 项目文件夹下（script-tool-v4/exports），
# 可用环境变量 SCRIPT_TOOL_EXPORT_DIR 或界面手动更改保存位置
EXPORT_DIR = Path(os.getenv("SCRIPT_TOOL_EXPORT_DIR", "").strip() or (BASE_DIR / "exports"))
DASHSCOPE_API_KEY = os.getenv("SCRIPT_TOOL_DASHSCOPE_API_KEY") or OPENAI_API_KEY
WANX_IMAGE_MODEL = os.getenv("SCRIPT_TOOL_WANX_MODEL", "wanx-v1")
KLING_VIDEO_MODEL = os.getenv("SCRIPT_TOOL_KLING_MODEL", "kling/kling-v3-video-generation")
KLING_OMNI_MODEL = os.getenv("SCRIPT_TOOL_KLING_OMNI_MODEL", "kling/kling-v3-omni-video-generation")
# ── v4：百炼新世代视频模型（统一走 video-generation/video-synthesis 端点）──
# happyhorse-1.1-i2v：单图（首帧）生视频；wan3.0-video：文生/首尾帧/参考（可串长视频）；
# happyhorse-1.1-r2v：多参考图生视频（跨场景保持角色一致性，最多 9 张参考图）。
WAN3_VIDEO_MODEL = os.getenv("SCRIPT_TOOL_WAN3_VIDEO_MODEL", "wan3.0-video")
HAPPYHORSE_I2V_MODEL = os.getenv("SCRIPT_TOOL_HAPPYHORSE_I2V_MODEL", "happyhorse-1.1-i2v")
HAPPYHORSE_R2V_MODEL = os.getenv("SCRIPT_TOOL_HAPPYHORSE_R2V_MODEL", "happyhorse-1.1-r2v")
# 分镜/工作台视频默认模型（角色一致性优先，故默认参考生视频）
VIDEO_MODEL_DEFAULT = os.getenv("SCRIPT_TOOL_VIDEO_MODEL_DEFAULT", HAPPYHORSE_R2V_MODEL)
# 专业级图像模型（千问图像 3.0 旗舰版）：角色形象图与三视图统一走它。
# 它经 multimodal-generation 接口生成，画质与语义遵循（五官/发型/服装/光影）
# 远优于 wanx 纯文生图，且支持传入参考图锁定人脸，故角色图默认全部改用它。
REF_IMAGE_MODEL = os.getenv("SCRIPT_TOOL_REF_IMAGE_MODEL", "qwen-image-3.0-pro")

# ── v6：角色配音（CosyVoice 语音合成，走 DashScope SDK，复用同一 DASHSCOPE_API_KEY）──
# CosyVoice v1 已下线；默认 v3-flash：音色最多(28+)、部分音色支持情感指令(Instruct)与字级时间戳。
# 可选 cosyvoice-v3-plus（音质最佳、音色少）/ cosyvoice-v2（稳定、但无情感指令）。
COSYVOICE_MODEL = os.getenv("SCRIPT_TOOL_COSYVOICE_MODEL", "cosyvoice-v3-flash")
# WebSocket 端点：留空用 SDK 默认；若用业务空间专属域名则填
# wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference。
COSYVOICE_WS_URL = os.getenv("SCRIPT_TOOL_COSYVOICE_WS_URL", "").strip()
# 默认音色（角色未单独配音色时用）：龙安洋(阳光大男孩，支持情感指令)。
COSYVOICE_DEFAULT_VOICE = os.getenv("SCRIPT_TOOL_COSYVOICE_VOICE", "longanyang")
# 合成音频格式：mp3（体积小、ffmpeg 混流友好）；可选 wav/pcm。
COSYVOICE_FORMAT = os.getenv("SCRIPT_TOOL_COSYVOICE_FORMAT", "mp3")


def _int_env(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "")).strip() or default)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, "")).strip() or default)
    except (TypeError, ValueError):
        return default


# 合成默认参数（可被角色/单句配置覆盖）：音量[0,100]、语速[0.5,2.0]、音调[0.5,2.0]
COSYVOICE_DEFAULT_VOLUME = _int_env("SCRIPT_TOOL_COSYVOICE_VOLUME", 50)
COSYVOICE_DEFAULT_SPEECH_RATE = _float_env("SCRIPT_TOOL_COSYVOICE_RATE", 1.0)
COSYVOICE_DEFAULT_PITCH_RATE = _float_env("SCRIPT_TOOL_COSYVOICE_PITCH", 1.0)
# 视频是否默认混入角色配音（关闭=仍输出无声视频，仅烧字幕）
VOICE_MUX_ENABLED = os.getenv("SCRIPT_TOOL_VOICE_MUX", "1").strip() not in ("0", "false", "False", "")
