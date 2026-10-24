"""v5：逐句定时字幕（多段 + 双语）——用 chained drawtext 烧录。

为什么用 drawtext 而不是 ass/subtitles 滤镜：drawtext + fontfile 已实测能在
Windows 用 imageio-ffmpeg 自带 ffmpeg 正确渲染中文（不依赖 fontconfig 找字体）。
每句字幕 = 一个 drawtext 滤镜，用 enable='between(t,start,end)' 控制出现/消失时间，
多句用逗号链式叠加。双语句把中/英写进同一个 textfile（换行分隔）。
本模块函数同步阻塞，路由层请用 asyncio.to_thread 调用。
"""
import math
import re
import subprocess
from pathlib import Path

from app.media.dashscope_media import _ffmpeg_exe, find_cjk_font

# 底部/顶部留白（像素）
_MARGIN = 48


# 字幕显示参数
_MAX_CHARS = 15        # 每行最多字符（超出折行，一般 ≤2 行）
_SPLIT_CHARS = 30      # 单句超过此长度（≈2 行）才按逗号再拆成多条 cue
_MIN_CUE_SEC = 1.1     # 每条 cue 最短显示秒数（避免一闪而过）
_MAX_CUE_SEC = 6.0     # 每条 cue 最长显示秒数（避免一句久留）
_READ_SPEED = 5.0      # 中文阅读速度（字/秒），用于估算理想时长
_MARKUP_PARENS = re.compile(r"[（(][^）)]*[）)]")
_QUOTES = "「」『』“”‘’《》\"'"


def _strip_markup(text: str) -> str:
    """去掉台词里的（表演提示）与「」等引号，只留可显示的文字。"""
    text = _MARKUP_PARENS.sub("", text or "")
    for q in _QUOTES:
        text = text.replace(q, "")
    return text


def _split_long(s: str, max_chars: int = _SPLIT_CHARS) -> list:
    """句子超过 max_chars（约两行）才按逗号/顿号再拆；否则整句作为一条 cue（烧录时折行）。"""
    s = s.strip()
    if not s:
        return []
    if len(s) <= max_chars:
        return [s]
    out, cur = [], ""
    for ch in s:
        cur += ch
        if ch in "，、：,:" and len(cur.strip()) >= 8:
            out.append(cur.strip())
            cur = ""
    rem = cur.strip()
    while len(rem) > max_chars:
        out.append(rem[:max_chars])
        rem = rem[max_chars:]
    if rem:
        out.append(rem)
    return [x.rstrip("，、：,:").strip() for x in out if x.strip()]


def _assign_timing(cues: list, duration: float) -> list:
    """分配每句显示时间，节奏均匀可读：

    - 每句理想时长 = clamp(字数/阅读速度, 最短, 最长)；
    - 时间充裕（理想总和 ≤ 镜头时长）：按比例拉伸填满，长句多停、短句少停；
    - 时间不够（台词太多）：先给每句"保底时长"，剩余再按理想比例分，
      避免短句被压到一闪而过、长短句忽快忽慢。
    """
    n = len(cues)
    if n == 0:
        return cues
    dur = max(0.5, float(duration or 5))
    ideal = [min(_MAX_CUE_SEC, max(_MIN_CUE_SEC, len(c["zh"]) / _READ_SPEED)) for c in cues]
    total = sum(ideal)
    if total <= dur:
        spans = [x * dur / total for x in ideal]
    else:
        floor = min(_MIN_CUE_SEC, dur / n)
        rest = max(0.0, dur - floor * n)
        rest_ideal = sum(max(0.0, x - floor) for x in ideal) or 1.0
        spans = [floor + max(0.0, x - floor) * rest / rest_ideal for x in ideal]
    t = 0.0
    for c, sp in zip(cues, spans):
        c["start"] = round(t, 2)
        t += sp
        c["end"] = round(min(t, dur), 2)
    cues[-1]["end"] = round(dur, 2)
    return cues



def split_dialogue_to_cues(text: str, duration: float, speakers=None,
                           max_cues: int = 20) -> list:
    """把整段台词清洗+按句切成 cues，并按阅读时长比例分配时间（节奏均匀）。

    - 去掉（表演提示）/「」引号；
    - 已知角色名（speakers）出现在句首"名字："时抽为 speaker，正文只留台词；
    - 以句末标点分句为主，单句超过约两行(30字)才按逗号再拆；
    - 时间按各句"阅读时长"比例分配并填满镜头，短句不闪、长句不久留。
    返回 [{"start","end","zh","en","speaker"}]。
    """
    text = _strip_markup(text or "")
    if not text.strip():
        return []
    names = [s for s in (speakers or []) if s]
    # 句级切分（保留句末标点）
    sentences, cur = [], ""
    for ch in text:
        cur += ch
        if ch in "。！？；!?；\n":
            sentences.append(cur)
            cur = ""
    if cur.strip():
        sentences.append(cur)

    segs = []   # [(speaker, text)]
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        spk = ""
        for name in names:
            for sep in ("：", ":"):
                if sent.startswith(name + sep):
                    spk = name
                    sent = sent[len(name) + 1:].strip()
                    break
            if spk:
                break
        for piece in _split_long(sent):
            segs.append((spk, piece))
    segs = segs[:max_cues]
    if not segs:
        return []

    cues = [{"start": 0.0, "end": 0.0, "zh": txt, "en": "", "speaker": spk}
            for spk, txt in segs]
    return _assign_timing(cues, duration)



def default_subtitles(dialogue: str, duration: float, speakers=None) -> dict:
    """由台词生成一份默认字幕配置（逐句、底部、中英双语预留）。"""
    return {"enabled": True, "position": "bottom", "bilingual": "both",
            "font_size": 34,
            "cues": split_dialogue_to_cues(dialogue, duration, speakers)}


def reading_time(cues) -> float:
    """一组 cue 的舒适阅读总时长（秒）：每句 max(最短时长, 字数/阅读速度)。"""
    return sum(max(_MIN_CUE_SEC, len((c.get("zh") or "")) / _READ_SPEED) for c in cues)


def suggest_split_count(cues, duration) -> int:
    """对白舒适阅读时长明显超过镜头时长时，建议拆成几个镜头。

    返回 1 表示无需拆分；否则 ceil(阅读时长/镜头时长)，且不超过句数。
    """
    if len(cues) < 2:
        return 1
    rt = reading_time(cues)
    dur = max(0.5, float(duration or 5))
    if rt <= dur * 1.25:            # 25% 以内算正常，不提示
        return 1
    return max(2, min(len(cues), math.ceil(rt / dur)))


def distribute_cues(cues, parts) -> list:
    """把 cues 按"字数权重"连续均分成 parts 组（保持顺序，不产生空组）。"""
    cues = list(cues)
    if parts <= 1 or len(cues) <= parts:
        if parts <= 1:
            return [cues]
        return [[c] for c in cues]
    weights = [max(1.0, len((c.get("zh") or ""))) for c in cues]
    total = sum(weights) or 1.0
    target = total / parts
    groups, cur, acc = [], [], 0.0
    for c, w in zip(cues, weights):
        cur.append(c)
        acc += w
        if acc >= target and len(groups) < parts - 1:
            groups.append(cur)
            cur, acc = [], 0.0
    if cur:
        groups.append(cur)
    return groups




def probe_duration(video_path) -> float:
    """用 ffmpeg 读取视频时长（秒），失败返回 0。"""
    exe = _ffmpeg_exe()
    try:
        p = subprocess.run([exe, "-i", str(video_path)],
                           capture_output=True, text=True)
    except FileNotFoundError:
        return 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr or "")
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 0.0


def _wrap(text: str, max_chars: int) -> str:
    """按字符数把长文本折成多行（drawtext 不自动换行，必须手动折行防溢出）。"""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    lines, cur = [], ""
    for ch in text:
        cur += ch
        if len(cur) >= max_chars:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def _cue_text(cue: dict, bilingual: str, max_chars: int = _MAX_CHARS) -> str:
    """按双语模式拼一句字幕文本（中/英各自折行）。

    说话人（speaker）仅用于对应角色，不显示在视频字幕里。
    """
    zh = (cue.get("zh") or "").strip()
    en = (cue.get("en") or "").strip()
    lines = []
    if bilingual in ("both", "zh") and zh:
        lines.append(_wrap(zh, max_chars))
    if bilingual in ("both", "en") and en:
        lines.append(_wrap(en, max_chars * 2))   # 英文字符窄，放宽每行字数
    return "\n".join(lines)



def _yexpr(position: str) -> str:
    if position == "center":
        return "(h-th)/2"
    if position == "top":
        return str(_MARGIN)
    return f"h-th-{_MARGIN}"   # bottom（默认）


def burn_subtitles_timed(video_path, cfg: dict, out_path=None, font: str = None) -> str:
    """按 cfg 逐句定时烧录字幕，返回输出视频路径。cfg 见 default_subtitles。

    - 无启用/无有效句 → 原样返回不烧录；
    - 每句一个 drawtext + enable='between(t,start,end)'，链式叠加；
    - 时间会按真实时长夹取，避免越界。
    """
    cfg = cfg or {}
    if not cfg.get("enabled", True):
        return str(video_path)
    cues = [c for c in (cfg.get("cues") or [])
            if (c.get("zh") or c.get("en") or "").strip()]
    if not cues:
        return str(video_path)
    font = font or find_cjk_font()
    if not font:
        raise RuntimeError("未找到中文字体，无法烧录字幕")

    exe = _ffmpeg_exe()
    vp = Path(video_path)
    out = Path(out_path) if out_path else vp.with_name(vp.stem + "_sub.mp4")
    duration = probe_duration(vp) or 0.0
    bilingual = cfg.get("bilingual", "both")
    position = cfg.get("position", "bottom")
    try:
        fontsize = int(cfg.get("font_size") or 34)
    except (TypeError, ValueError):
        fontsize = 34
    fontfile = "'" + font.replace(":", "\\:") + "'"
    yexpr = _yexpr(position)

    tmpfiles, filters = [], []
    for i, cue in enumerate(cues):
        text = _cue_text(cue, bilingual)
        if not text:
            continue
        try:
            start = float(cue.get("start") or 0)
        except (TypeError, ValueError):
            start = 0.0
        try:
            end = float(cue.get("end") or 0) or duration
        except (TypeError, ValueError):
            end = duration
        if duration > 0:
            start = max(0.0, min(start, max(0.0, duration - 0.1)))
            end = max(start + 0.2, min(end, duration))
        if end <= start:
            end = start + 0.5
        tf = vp.with_name(f"{vp.stem}_cue{i}.txt")
        tf.write_text(text.replace("\\", "\\\\").replace("%", "%%"), encoding="utf-8")
        tmpfiles.append(tf)
        filters.append(
            f"drawtext=fontfile={fontfile}:textfile={tf.name}:fontsize={fontsize}"
            f":fontcolor=white:borderw=2:bordercolor=black@0.85"
            f":x=(w-text_w)/2:y={yexpr}:enable='between(t,{start:.2f},{end:.2f})'")

    if not filters:
        return str(video_path)

    vf = ",".join(filters)
    cmd = [exe, "-y", "-i", vp.name, "-vf", vf,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out.name]
    try:
        proc = subprocess.run(cmd, cwd=str(vp.parent), capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("未找到 ffmpeg：请安装 imageio-ffmpeg（pip install imageio-ffmpeg）")
    finally:
        for tf in tmpfiles:
            try:
                tf.unlink()
            except OSError:
                pass
    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"字幕烧录失败：{(proc.stderr or '')[-400:]}")
    return str(out)
