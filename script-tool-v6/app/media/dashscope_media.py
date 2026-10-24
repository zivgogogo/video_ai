"""v3：DashScope 媒体生成异步客户端（wanx 文生图 / 可灵视频生成 / 任务轮询）。"""
import asyncio
import base64
import mimetypes
import subprocess
from pathlib import Path

import httpx

from app.config import (DASHSCOPE_API_KEY, WANX_IMAGE_MODEL,
                        KLING_VIDEO_MODEL, KLING_OMNI_MODEL, REF_IMAGE_MODEL,
                        WAN3_VIDEO_MODEL, HAPPYHORSE_I2V_MODEL,
                        HAPPYHORSE_R2V_MODEL, VIDEO_MODEL_DEFAULT)

BASE = "https://dashscope.aliyuncs.com"
# 新世代 multimodal-generation 接口：qwen-image-3.0 / wan2.7 系列走这里，
# 支持在 messages 里同时传参考图与指令（I2I），可锁定人脸/发型/服装。
MM_URL = f"{BASE}/api/v1/services/aigc/multimodal-generation/generation"
# 视频生成端点（可灵 / happyhorse / wan3.0 共用同一路径，均为异步任务）。
VIDEO_GEN_URL = f"{BASE}/api/v1/services/aigc/video-generation/video-synthesis"

_SIZE_MAP = {"16:9": "1280*720", "1:1": "1024*1024", "9:16": "720*1280",
             "9:16_portrait": "720*1280"}


def _headers(async_enable: bool = True) -> dict:
    h = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}",
         "Content-Type": "application/json"}
    if async_enable:
        h["X-DashScope-Async"] = "enable"
    return h


async def submit_image_task(prompt: str, size: str = "1:1", n: int = 1) -> str:
    """提交 wanx 文生图任务，返回 task_id。

    n: 单任务生成张数。注意部分模型（如 qwen-image 系列）只支持 n=1，
    需要多张时优先用并发多次调用 submit_image_task 的方式，见 gen_candidates。
    """
    payload = {
        "model": WANX_IMAGE_MODEL,
        "input": {"prompt": prompt},
        "parameters": {"size": _SIZE_MAP.get(size, size), "n": max(1, int(n))},
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/api/v1/services/aigc/text2image/image-synthesis",
                         headers=_headers(), json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"文生图提交失败({r.status_code}): {r.text[:300]}")
        task_id = r.json().get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"未获取任务ID: {r.text[:300]}")
        return task_id


async def submit_video_task(prompt: str, media_urls: list = None,
                            duration: int = 5, aspect_ratio: str = "16:9",
                            mode: str = "std") -> dict:
    """提交可灵视频任务。带角色参考图时使用 omni 模型（角色一致性）。

    返回 {"task_id", "model"}。
    """
    use_omni = bool(media_urls)
    model = KLING_OMNI_MODEL if use_omni else KLING_VIDEO_MODEL
    input_data = {"prompt": prompt, "multi_shot": False, "shot_type": "customize"}
    if use_omni:
        input_data["media"] = [{"type": "refer", "url": u} for u in media_urls]
        input_data["element_list"] = [{"element_id": i}
                                      for i in range(1, len(media_urls) + 1)]
    payload = {
        "model": model,
        "input": input_data,
        "parameters": {"mode": mode, "aspect_ratio": aspect_ratio,
                       "duration": int(duration), "audio": False,
                       "watermark": False},
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/api/v1/services/aigc/video-generation/video-synthesis",
                         headers=_headers(), json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"视频任务提交失败({r.status_code}): {r.text[:300]}")
        task_id = r.json().get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"未获取任务ID: {r.text[:300]}")
        return {"task_id": task_id, "model": model}


# ── v4：百炼新世代视频模型（happyhorse / wan3.0，统一 media 数组结构）──

def first_frame_media(url: str) -> list:
    """首帧生视频（i2v）的 media：仅 1 张 first_frame。"""
    return [{"type": "first_frame", "url": url}]


def first_last_media(first_url: str, last_url: str) -> list:
    """首尾帧生视频（wan3.0）的 media：first_frame + last_frame。"""
    m = [{"type": "first_frame", "url": first_url}]
    if last_url:
        m.append({"type": "last_frame", "url": last_url})
    return m


def ref_media(urls: list) -> list:
    """参考生视频（r2v）的 media：1-9 张 reference_image（按顺序对应 [Image N]）。"""
    return [{"type": "reference_image", "url": u} for u in (urls or []) if u]


def model_duration_range(model: str) -> tuple:
    """模型支持的时长范围（秒）：wan3.0 为 2–30，happyhorse 为 3–15。"""
    if str(model).startswith("wan3"):
        return 2, 30
    return 3, 15


def _clamp_duration(model: str, duration) -> int:
    """按模型能力夹取时长：wan3.0 为 [2,30] 或 -1（智能）；happyhorse 为 [3,15]。"""
    try:
        d = int(duration)
    except (TypeError, ValueError):
        d = 5
    lo, hi = model_duration_range(model)
    if str(model).startswith("wan3") and d == -1:
        return -1
    return max(lo, min(hi, d))


async def submit_video_unified(model: str, prompt: str, media: list = None,
                               resolution: str = "720P", ratio: str = None,
                               duration: int = 5, audio: bool = False,
                               prompt_extend: bool = None, watermark: bool = False,
                               seed: int = None) -> dict:
    """提交 happyhorse / wan3.0 视频任务，返回 {"task_id", "model"}。

    与旧 submit_video_task（可灵）的区别：新模型用 input.media=[{type,url}]，
    type ∈ first_frame/last_frame/reference_image；参数按模型能力裁剪：
    - happyhorse-1.1-i2v：不支持 ratio/audio（比例随首帧），watermark 默认 true→显式传 false；
    - happyhorse-1.1-r2v：支持 ratio，不支持 audio；
    - wan3.0-video：支持 ratio/audio/prompt_extend。
    media 里的 url 可为公网链接或 base64 data-uri（本地图统一走 base64）。
    """
    model = (model or VIDEO_MODEL_DEFAULT).strip()
    input_data = {}
    if prompt:
        input_data["prompt"] = prompt
    if media:
        input_data["media"] = media
    if not input_data:
        raise RuntimeError("视频任务缺少 prompt 或 media")

    is_wan3 = model.startswith("wan3")
    supports_ratio = not model.endswith("i2v")   # i2v 比例随首帧，不接受 ratio

    params = {"resolution": resolution or "720P",
              "duration": _clamp_duration(model, duration),
              "watermark": bool(watermark)}
    if ratio and supports_ratio:
        params["ratio"] = ratio
    if is_wan3:
        params["audio"] = bool(audio)            # 项目偏好无声视频，默认 audio=False
        if prompt_extend is not None:
            params["prompt_extend"] = bool(prompt_extend)
    if seed is not None:
        params["seed"] = int(seed)

    payload = {"model": model, "input": input_data, "parameters": params}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(VIDEO_GEN_URL, headers=_headers(), json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"视频任务提交失败({r.status_code}): {r.text[:300]}")
        task_id = r.json().get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"未获取任务ID: {r.text[:300]}")
        return {"task_id": task_id, "model": model}


def _ffmpeg_exe() -> str:
    """返回 ffmpeg 可执行文件：优先 imageio-ffmpeg 自带二进制，回退 PATH 上的 ffmpeg。"""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# 中文字体候选（烧字幕用，按顺序取第一个存在的）
_CJK_FONTS = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
              "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
              "/System/Library/Fonts/PingFang.ttc",
              "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]


def find_cjk_font() -> str:
    """找一个可用的中文字体文件路径，找不到返回空串。"""
    for f in _CJK_FONTS:
        try:
            if Path(f).exists():
                return f
        except OSError:
            continue
    return ""


def extract_last_frame(video_path, out_path) -> str:
    """用 ffmpeg 抽取视频末帧存为图片，返回 out_path（用于承接长视频）。

    先试 -sseof 快速定位末帧；失败则全量解码配合 -update 1 覆盖，末帧留在输出文件。
    本函数同步阻塞，路由层请用 asyncio.to_thread 调用。
    """
    exe = _ffmpeg_exe()
    vp, op = str(video_path), str(out_path)
    attempts = [
        [exe, "-y", "-sseof", "-0.1", "-i", vp,
         "-update", "1", "-frames:v", "1", "-q:v", "2", op],
        [exe, "-y", "-i", vp, "-update", "1", "-q:v", "2", op],
    ]
    err = ""
    for cmd in attempts:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError("未找到 ffmpeg：请安装 imageio-ffmpeg（pip install imageio-ffmpeg）")
        if proc.returncode == 0 and Path(op).exists() and Path(op).stat().st_size > 0:
            return op
        err = (proc.stderr or "")[-300:]
    raise RuntimeError(f"抽取末帧失败：{err}")


def burn_subtitle(video_path, text, out_path=None, fontsize: int = 34,
                  margin: int = 52, font: str = None) -> str:
    """用 ffmpeg drawtext 把台词烧录成视频底部中文字幕，返回输出视频路径。

    - 字幕铺满整段（无需时间轴），底部居中，白字黑边；
    - text 里的换行会渲染成多行（多句对白/旁白可分行）；
    - 依赖 drawtext(libfreetype)，imageio-ffmpeg 自带构建已包含。
    本函数同步阻塞，路由层请用 asyncio.to_thread 调用。
    """
    text = (text or "").strip()
    if not text:
        return str(video_path)
    font = font or find_cjk_font()
    if not font:
        raise RuntimeError("未找到中文字体，无法烧录字幕")
    exe = _ffmpeg_exe()
    vp = Path(video_path)
    out = Path(out_path) if out_path else vp.with_name(vp.stem + "_sub.mp4")
    txt = vp.with_name(vp.stem + "_subtxt.txt")
    # drawtext 会对文本做 % 与 \ 展开，先转义；换行保留为真实换行
    safe = text.replace("\\", "\\\\").replace("%", "%%")
    txt.write_text(safe, encoding="utf-8")
    # Windows 盘符冒号需转义为 \:，且整个值加单引号，才能让 drawtext 解析器
    # 正确收到 C\:/... 而不被当成选项分隔符（实测：不加引号会报 Invalid argument）。
    fontfile = "'" + font.replace(":", "\\:") + "'"
    vf = (f"drawtext=fontfile={fontfile}:textfile={txt.name}"
          f":fontsize={fontsize}:fontcolor=white:borderw=2:bordercolor=black@0.85"
          f":x=(w-text_w)/2:y=h-th-{margin}")
    # 用 cwd + 相对文件名，避开输入/输出/textfile 路径的转义问题
    cmd = [exe, "-y", "-i", vp.name, "-vf", vf,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out.name]
    try:
        proc = subprocess.run(cmd, cwd=str(vp.parent), capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("未找到 ffmpeg：请安装 imageio-ffmpeg（pip install imageio-ffmpeg）")
    finally:
        try:
            txt.unlink()
        except OSError:
            pass
    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"字幕烧录失败：{(proc.stderr or '')[-300:]}")
    return str(out)


async def get_task(task_id: str) -> dict:
    """查询异步任务状态，返回 output 字典。"""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/api/v1/tasks/{task_id}",
                        headers=_headers(async_enable=False))
        r.raise_for_status()
        return r.json().get("output", {})


async def wait_task(task_id: str, timeout: int = 600, interval: int = 5) -> dict:
    """轮询直到任务完成，返回 output 字典（含 results / video_url）。"""
    elapsed = 0
    while elapsed < timeout:
        out = await get_task(task_id)
        status = out.get("task_status", "UNKNOWN")
        if status == "SUCCEEDED":
            return out
        if status in ("FAILED", "CANCELLED", "UNKNOWN_ERROR"):
            raise RuntimeError(f"任务失败[{status}]: {out.get('message', '')[:300]}")
        await asyncio.sleep(interval)
        elapsed += interval
    raise RuntimeError(f"任务超时({timeout}s): {task_id}")


async def gen_one_image(prompt: str, size: str = "1:1",
                        timeout: int = 300, interval: int = 5) -> str:
    """提交并等待单张文生图，返回远程图片 URL。"""
    task_id = await submit_image_task(prompt, size=size, n=1)
    output = await wait_task(task_id, timeout=timeout, interval=interval)
    return image_url_from_output(output)


async def gen_images_concurrent(prompt: str, count: int = 3, size: str = "1:1",
                                timeout: int = 300, interval: int = 5) -> dict:
    """并发提交 count 个独立的单图任务，返回 {"urls": [...], "errors": [...]}。

    采用「并发多个 n=1 任务」而非「单任务 n=count」，原因：
    1. 不受模型 n 参数上限限制（qwen-image 系列仅支持 n=1）；
    2. 单张失败不影响其余，容错更好；
    3. 总耗时接近单张，而非 count 倍。
    至少要有 1 张成功，否则抛出汇总异常。
    """
    count = max(1, int(count))
    tasks = [gen_one_image(prompt, size=size, timeout=timeout, interval=interval)
             for _ in range(count)]
    settled = await asyncio.gather(*tasks, return_exceptions=True)

    urls, errors = [], []
    for i, r in enumerate(settled, 1):
        if isinstance(r, Exception):
            errors.append(f"第{i}张: {str(r)[:180]}")
        elif r:
            urls.append(r)

    if not urls:
        raise RuntimeError("；".join(errors) or "全部图片生成失败")
    return {"urls": urls, "errors": errors}


# ── 新世代 multimodal 接口（参考图锁脸）─────────────────────

def file_to_data_uri(path, max_bytes: int = 9 * 1024 * 1024) -> str:
    """把本地图片读成 base64 data-uri，供 multimodal / 视频接口作参考图或首帧。

    本地服务上的图片阿里云无法回拉，OSS 结果链接又带过期时间，
    因此参考图/首帧统一用 base64 内嵌传输。
    max_bytes 默认 9MB（multimodal 图像接口上限 10MB）；happyhorse/wan3.0 视频
    图像上限 20MB，需更大时传入 max_bytes（base64 会膨胀约 33%，建议留余量）。
    """
    data = Path(path).read_bytes()
    if len(data) > max_bytes:
        raise RuntimeError(f"图片过大（{len(data) // 1024}KB），超过 {max_bytes // 1024 // 1024}MB 限制")
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def image_url_from_multimodal_output(output: dict) -> str:
    """解析 multimodal-generation 响应：output.choices[].message.content[].image。"""
    for ch in output.get("choices") or []:
        content = (ch.get("message") or {}).get("content") or []
        for item in content:
            if isinstance(item, dict) and item.get("image"):
                return item["image"]
    urls = image_urls_from_output(output)   # 兼容旧 results 结构
    if urls:
        return urls[0]
    raise RuntimeError("multimodal 响应中没有图片")


async def _post_multimodal(payload: dict, async_enable: bool, timeout: int):
    async with httpx.AsyncClient(timeout=timeout) as c:
        return await c.post(MM_URL, headers=_headers(async_enable=async_enable),
                            json=payload)


async def call_multimodal_image(prompt: str, image_inputs: list = None,
                                size: str = "16:9", model: str = None,
                                prompt_extend: bool = False,
                                timeout: int = 300, interval: int = 5) -> str:
    """调用 multimodal-generation 并返回远程图片 URL（同步优先，异步兑底）。

    为什么同步优先：部分 API Key 对该接口报 403 AccessDenied
    （current user api does not support asynchronous calls），
    而千问图像 3.0 系列官方支持同步调用，故默认同步；
    若服务端强制异步（响应里带 task_id）或拒绝同步，再自动切异步轮询。
    """
    content = [{"image": u} for u in (image_inputs or [])]
    content.append({"text": prompt})
    payload = {
        "model": model or REF_IMAGE_MODEL,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {"size": _SIZE_MAP.get(size, size),
                       "prompt_extend": bool(prompt_extend)},
    }

    r = await _post_multimodal(payload, async_enable=False, timeout=timeout)
    if r.status_code == 200:
        out = r.json().get("output", {})
        if out.get("task_id"):      # 服务端把请求转成了异步任务
            out = await wait_task(out["task_id"], timeout=timeout, interval=interval)
        return image_url_from_multimodal_output(out)

    # 同步被拒（如该 Key 仅允许异步）→ 回退异步
    if r.status_code == 403 or "asynchronous" in r.text.lower():
        r2 = await _post_multimodal(payload, async_enable=True, timeout=60)
        if r2.status_code == 200:
            task_id = r2.json().get("output", {}).get("task_id")
            if task_id:
                out = await wait_task(task_id, timeout=timeout, interval=interval)
                return image_url_from_multimodal_output(out)
        raise RuntimeError(f"multimodal 异步提交失败({r2.status_code}): {r2.text[:300]}")

    raise RuntimeError(f"multimodal 提交失败({r.status_code}): {r.text[:300]}")


async def submit_multimodal_image(prompt: str, image_inputs: list = None,
                                  size: str = "16:9", model: str = None,
                                  prompt_extend: bool = False) -> str:
    """[兼容保留] 仅提交异步任务返回 task_id；新代码请用 call_multimodal_image。"""
    content = [{"image": u} for u in (image_inputs or [])]
    content.append({"text": prompt})
    payload = {
        "model": model or REF_IMAGE_MODEL,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {"size": _SIZE_MAP.get(size, size),
                       "prompt_extend": bool(prompt_extend)},
    }
    r = await _post_multimodal(payload, async_enable=True, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"multimodal 提交失败({r.status_code}): {r.text[:300]}")
    task_id = r.json().get("output", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"未获取任务ID: {r.text[:300]}")
    return task_id


async def gen_image_with_reference(prompt: str, reference=None,
                                   size: str = "16:9", model: str = None,
                                   timeout: int = 300, interval: int = 5) -> str:
    """带参考图生成单张图，返回远程图片 URL。

    reference 可以是本地图片路径（自动转 base64）、公网 URL 或 data-uri。
    """
    images = []
    if reference:
        s = str(reference)
        if s.startswith(("http://", "https://", "data:")):
            images.append(s)
        else:
            images.append(file_to_data_uri(reference))
    return await call_multimodal_image(prompt, image_inputs=images, size=size,
                                       model=model, timeout=timeout,
                                       interval=interval)


# ── 旗舰模型纯文生图（角色形象图专用）─────────────────────

async def gen_one_image_pro(prompt: str, size: str = "9:16", model: str = None,
                            timeout: int = 300, interval: int = 5) -> str:
    """用旗舰多模态模型（默认 qwen-image-3.0-pro）纯文生图，返回远程图片 URL。

    与 gen_one_image 的区别：qwen-image-3.0 系列走 multimodal-generation 接口，
    画质与语义遵循（五官/发型/服装/光影）显著优于 wanx 纯文生图，人物更专业耐看。
    model 传 None 时回落到 REF_IMAGE_MODEL。
    """
    return await call_multimodal_image(prompt, image_inputs=None, size=size,
                                       model=model, timeout=timeout,
                                       interval=interval)


async def gen_images_concurrent_pro(prompt: str, count: int = 3, size: str = "9:16",
                                    model: str = None, timeout: int = 300,
                                    interval: int = 5) -> dict:
    """并发用旗舰模型生成 count 张候选图，返回 {"urls": [...], "errors": [...]}。

    沿用 gen_images_concurrent 的「并发多个单图任务」策略（容错好、总耗时≈单张），
    只是把底层模型换成画质更高的 multimodal 旗舰模型。至少 1 张成功，否则抛汇总异常。
    """
    count = max(1, int(count))
    tasks = [gen_one_image_pro(prompt, size=size, model=model,
                               timeout=timeout, interval=interval)
             for _ in range(count)]
    settled = await asyncio.gather(*tasks, return_exceptions=True)

    urls, errors = [], []
    for i, r in enumerate(settled, 1):
        if isinstance(r, Exception):
            errors.append(f"第{i}张: {str(r)[:180]}")
        elif r:
            urls.append(r)

    if not urls:
        raise RuntimeError("；".join(errors) or "全部图片生成失败")
    return {"urls": urls, "errors": errors}


async def download_file(url: str, path) -> str:
    """下载远程文件到本地路径。"""
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(url)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    return str(path)


def image_urls_from_output(output: dict) -> list:
    """返回任务结果中的全部图片 URL（按顺序）。"""
    urls = [it.get("url") for it in output.get("results", []) if it.get("url")]
    return urls


def image_url_from_output(output: dict) -> str:
    urls = image_urls_from_output(output)
    if urls:
        return urls[0]
    raise RuntimeError("任务结果中没有图片URL")


def video_url_from_output(output: dict) -> str:
    url = output.get("video_url") or ""
    if not url:
        vids = output.get("results", [])
        if vids:
            url = vids[0].get("url", "")
    if not url:
        raise RuntimeError("任务结果中没有视频URL")
    return url
