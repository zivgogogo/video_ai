"""统一的 .env 加载器。

优先使用 python-dotenv；未安装时回退到内置简易解析。
所有脚本的密钥只从这里（.env / 系统环境变量）读取，代码中不再出现明文 Key。
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse_env_file(path: Path) -> None:
    """最简 .env 解析：逐行读取 KEY=VALUE，已存在的环境变量不覆盖。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_env(start_dir: Path | str | None = None) -> Path | None:
    """从 start_dir（默认本文件所在目录）向上查找最近的 .env 并加载。

    返回实际加载的文件路径；未找到时返回 None。
    """
    if start_dir is None:
        start_dir = Path(__file__).resolve().parent
    start_dir = Path(start_dir).resolve()
    for directory in (start_dir, *start_dir.parents):
        candidate = directory / ".env"
        if not candidate.is_file():
            continue
        try:
            from dotenv import load_dotenv
        except ImportError:
            _parse_env_file(candidate)
        else:
            load_dotenv(candidate, override=False)
        return candidate
    return None