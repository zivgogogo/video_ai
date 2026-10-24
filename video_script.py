"""
HappyHorse 文生视频 (Text-to-Video) 脚本
模型：happyhorse-1.0-t2v
API文档：https://bailian.console.aliyun.com/cn-beijing?tab=api#/api/?type=model&url=3029820c
采用异步轮询方式请求（创建任务 -> 轮询获取结果）
"""

import base64
import mimetypes
import os
import time
import json
import requests

from env_loader import load_env

# API Key 统一从项目根目录 .env / 系统环境变量读取
load_env()
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
if not DASHSCOPE_API_KEY:
    raise RuntimeError("未配置 DASHSCOPE_API_KEY，请在 .env 或系统环境变量中设置")

# 华北2（北京）Endpoint
CREATE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
QUERY_TASK_URL_TEMPLATE = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"

# 轮询配置
POLL_INTERVAL_SECONDS = 15  # 建议15秒
MAX_POLL_ATTEMPTS = 40  # 15s * 40 = 10分钟超时


def create_video_task(
    prompt: str,
    resolution: str = "1080P",
    # resolution 可选值: "720P", "1080P"（默认值）
    ratio: str = "16:9",
    # ratio 可选值: "16:9"（默认值）, "9:16", "1:1", "4:3", "3:4", "4:5", "5:4"
    duration: int = 5,
    # duration 取值范围: [3, 15] 之间的整数，单位秒，默认值5
    watermark: bool = True,
    # watermark 可选值: True（默认，右下角添加"Happy Horse"水印）, False（不添加水印）
    seed: int = None,
    # seed 取值范围: [0, 2147483647]，未指定时系统自动生成随机种子
    # 固定seed可提升可复现性，但不能保证每次完全一致
) -> dict:
    """
    步骤1：创建文生视频任务，返回 task_id

    Args:
        prompt: 文本提示词，支持任何语言，长度不超过5000个非中文字符或2500个中文字符
        resolution: 视频分辨率档位
        ratio: 视频宽高比
        duration: 视频时长（秒）
        watermark: 是否添加水印
        seed: 随机数种子
    """
    headers = {
        "Content-Type": "application/json",  # 必选
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",  # 必选
        "X-DashScope-Async": "enable",  # 必选，HTTP只支持异步，缺少会报错
    }

    payload = {
        # "model": "happyhorse-1.1-t2v",  # model 可选值: "happyhorse-1.0-t2v"
        "model": "wan3.0-video",
        "input": {
            "prompt": prompt,
        },
        "parameters": {
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "watermark": watermark,
        },
    }

    if seed is not None:
        payload["parameters"]["seed"] = seed

    print(f"[创建任务] prompt: {prompt[:80]}...")
    print(f"[参数] resolution={resolution}, ratio={ratio}, duration={duration}s, watermark={watermark}, seed={seed}")

    response = requests.post(CREATE_TASK_URL, headers=headers, json=payload)
    result = response.json()

    if response.status_code != 200:
        print(f"[错误] HTTP {response.status_code}: {result}")
        return result

    if "output" in result and "task_id" in result["output"]:
        print(f"[成功] task_id: {result['output']['task_id']}, status: {result['output']['task_status']}")
    else:
        print(f"[异常] 响应无task_id: {result}")

    return result


# ── 图生视频（首帧）：happyhorse-1.1-i2v，比例随首帧图片，不支持 ratio ──
I2V_MODEL = "happyhorse-1.1-i2v"
# 图像输入上限 20MB，base64 会膨胀，取 18MB 原始字节留余量
IMAGE_MAX_BYTES = 18 * 1024 * 1024


def _image_data_uri(image_path: str) -> str:
    """本地图片转 base64 data-uri（i2v 的 media.url 支持 data-uri）。"""
    size = os.path.getsize(image_path)
    if size > IMAGE_MAX_BYTES:
        raise ValueError(f"图片过大: {size / 1024 / 1024:.2f}MB > 18MB")
    mime = mimetypes.guess_type(image_path)[0] or "image/png"
    with open(image_path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def create_image_video_task(
    prompt: str,
    image_path: str,
    resolution: str = "1080P",
    # resolution 可选值: "720P", "1080P"（默认）
    duration: int = 5,
    # duration 取值范围: [3, 15] 之间的整数，单位秒（happyhorse 上限 15s）
    watermark: bool = False,
    # 提示词要求画面无水印，故默认 False
    seed: int = None,
) -> dict:
    """
    步骤1：创建图生视频任务（首帧），返回 task_id

    宽高比随首帧图片，无需也不能传 ratio。
    """
    headers = {
        "Content-Type": "application/json",  # 必选
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",  # 必选
        "X-DashScope-Async": "enable",  # 必选，HTTP只支持异步
    }

    payload = {
        "model": I2V_MODEL,
        "input": {
            "prompt": prompt,
            "media": [{"type": "first_frame", "url": _image_data_uri(image_path)}],
        },
        "parameters": {
            "resolution": resolution,
            "duration": duration,
            "watermark": watermark,
        },
    }

    if seed is not None:
        payload["parameters"]["seed"] = seed

    print(f"[创建任务] model={I2V_MODEL}, 首帧={image_path}")
    print(f"[参数] resolution={resolution}, duration={duration}s, watermark={watermark}, seed={seed}")

    response = requests.post(CREATE_TASK_URL, headers=headers, json=payload)
    result = response.json()

    if response.status_code != 200:
        print(f"[错误] HTTP {response.status_code}: {result}")
        return result

    if "output" in result and "task_id" in result["output"]:
        print(f"[成功] task_id: {result['output']['task_id']}, status: {result['output']['task_status']}")
    else:
        print(f"[异常] 响应无task_id: {result}")

    return result


def image_to_video(
    prompt: str,
    image_path: str,
    resolution: str = "1080P",
    duration: int = 5,
    watermark: bool = False,
    seed: int = None,
    output_path: str = None,
) -> str:
    """
    完整流程（图生视频）：图片作首帧 → 创建任务 → 轮询 → 返回视频URL（可选下载）

    Returns:
        视频URL 或 本地文件路径
    """
    create_result = create_image_video_task(
        prompt=prompt,
        image_path=image_path,
        resolution=resolution,
        duration=duration,
        watermark=watermark,
        seed=seed,
    )

    task_id = create_result.get("output", {}).get("task_id")
    if not task_id:
        error_msg = create_result.get("message", "未知错误")
        raise RuntimeError(f"创建任务失败: {error_msg}")

    print(f"\n[轮询] 间隔{POLL_INTERVAL_SECONDS}s, 最长等待{POLL_INTERVAL_SECONDS * MAX_POLL_ATTEMPTS}s")
    final_result = poll_until_complete(task_id)
    status = final_result.get("output", {}).get("task_status", "UNKNOWN")

    if status == "SUCCEEDED":
        video_url = final_result["output"]["video_url"]
        usage = final_result.get("usage", {})
        print(f"\n[完成] 视频生成成功!")
        print(f"[URL] {video_url}")
        print(f"[用量] {json.dumps(usage, ensure_ascii=False)}")

        if output_path:
            print(f"[下载] 保存到: {output_path}")
            video_resp = requests.get(video_url)
            with open(output_path, "wb") as f:
                f.write(video_resp.content)
            print(f"[完成] 文件大小: {len(video_resp.content) / 1024 / 1024:.2f} MB")
            return output_path

        return video_url

    elif status == "FAILED":
        code = final_result.get("output", {}).get("code", "")
        message = final_result.get("output", {}).get("message", "未知错误")
        raise RuntimeError(f"视频生成失败: [{code}] {message}")
    elif status == "CANCELED":
        raise RuntimeError("任务已被取消")
    else:
        raise RuntimeError(f"任务状态异常: {status}")


def query_task_result(task_id: str) -> dict:
    """步骤2：根据 task_id 查询任务结果（task_id 有效期24小时）"""
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
    }
    url = QUERY_TASK_URL_TEMPLATE.format(task_id=task_id)
    response = requests.get(url, headers=headers)
    return response.json()


def poll_until_complete(task_id: str) -> dict:
    """
    轮询任务状态直到终态

    状态流转: PENDING → RUNNING → SUCCEEDED / FAILED
    终态: SUCCEEDED, FAILED, CANCELED, UNKNOWN
    """
    terminal_states = {"SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"}

    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        result = query_task_result(task_id)
        status = result.get("output", {}).get("task_status", "UNKNOWN")
        print(f"  [轮询 {attempt}/{MAX_POLL_ATTEMPTS}] status={status}")

        if status in terminal_states:
            return result

        time.sleep(POLL_INTERVAL_SECONDS)

    print("[超时] 达到最大轮询次数")
    return result


def text_to_video(
    prompt: str,
    resolution: str = "1080P",
    ratio: str = "16:9",
    duration: int = 5,
    watermark: bool = True,
    seed: int = None,
    output_path: str = None,
) -> str:
    """
    完整流程：创建任务 → 轮询 → 返回视频URL（可选下载）

    Args:
        prompt: 文本提示词
        resolution: 分辨率，可选 "720P" / "1080P"（默认）
        ratio: 宽高比，可选 "16:9"（默认） / "9:16" / "1:1" / "4:3" / "3:4" / "4:5" / "5:4"
        duration: 时长秒数，[3,15]整数，默认5
        watermark: 水印开关，默认True
        seed: 随机种子，[0,2147483647]，None为随机
        output_path: 本地保存路径（可选，不传只返回URL）

    Returns:
        视频URL 或 本地文件路径
    """
    # 创建任务
    create_result = create_video_task(
        prompt=prompt,
        resolution=resolution,
        ratio=ratio,
        duration=duration,
        watermark=watermark,
        seed=seed,
    )

    task_id = create_result.get("output", {}).get("task_id")
    if not task_id:
        error_msg = create_result.get("message", "未知错误")
        raise RuntimeError(f"创建任务失败: {error_msg}")

    # 轮询等待
    print(f"\n[轮询] 间隔{POLL_INTERVAL_SECONDS}s, 最长等待{POLL_INTERVAL_SECONDS * MAX_POLL_ATTEMPTS}s")
    final_result = poll_until_complete(task_id)

    status = final_result.get("output", {}).get("task_status", "UNKNOWN")

    if status == "SUCCEEDED":
        video_url = final_result["output"]["video_url"]
        usage = final_result.get("usage", {})
        print(f"\n[完成] 视频生成成功!")
        print(f"[URL] {video_url}")
        print(f"[用量] {json.dumps(usage, ensure_ascii=False)}")

        if output_path:
            print(f"[下载] 保存到: {output_path}")
            video_resp = requests.get(video_url)
            with open(output_path, "wb") as f:
                f.write(video_resp.content)
            print(f"[完成] 文件大小: {len(video_resp.content) / 1024 / 1024:.2f} MB")
            return output_path

        return video_url

    elif status == "FAILED":
        code = final_result.get("output", {}).get("code", "")
        message = final_result.get("output", {}).get("message", "未知错误")
        raise RuntimeError(f"视频生成失败: [{code}] {message}")
    elif status == "CANCELED":
        raise RuntimeError("任务已被取消")
    else:
        raise RuntimeError(f"任务状态异常: {status}")


if __name__ == "__main__":
    # 提示词从 Markdown 文件读取（按照片适配后的版本）
    PROMPT_FILE = "视频提示词_山野人像_适配版.md"
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        test_prompt = f.read().strip()

    result = image_to_video(
        prompt=test_prompt,
        image_path="ref_portrait_mountain.png",  # 首帧参考图（比例随首帧）
        resolution="1080P",  # 可选: "720P", "1080P"
        duration=15,  # 时间轴到 15s，happyhorse 上限 15 秒
        watermark=False,  # 提示词要求画面无水印
        seed=None,  # 可选: 0~2147483647，None为随机
        output_path="output_mountain_i2v_15s.mp4",  # 可选: 不传只返回URL
    )
    print(f"\n最终结果: {result}")
