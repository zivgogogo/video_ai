#!/usr/bin/env python3
"""
千问文生图 - 简化版（带详细错误信息）
提交任务 -> 10秒轮询 -> 下载图片
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from urllib.parse import urlparse

# 复用项目根目录的统一 .env 加载器
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env_loader import load_env

load_env()

# 配置
PROMPT = ( 
'''
任务一：人物侧写报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 人物：苏青鱼

**年龄感**：看起来20岁左右（视觉年龄），大学生气质，外表年轻甜美，但神态中透着超越年龄的冷静与成熟。从原文"年纪轻轻"、"白皙甜美的女子"、"期末考试"可判断为学生身份，但行事果断老练。
**脸型**：鹅蛋脸，脸颊饱满白皙，带有胶原蛋白的年轻感。
**肤色**：肤色白皙，透着健康的血色，显得清透干净。原文描写"白皙甜美的女子"。
**眼睛**：杏眼，眼型圆润显甜美，但瞳孔黑白分明，眼神清澈且时刻保持警惕与冷静。在思考时眼神会变得锐利。
**眉毛**：淡眉，颜色不浓，形状平直略弯，给人一种温顺无害的错觉，符合"好女儿"的伪装需求。
**鼻子**：鼻梁挺直，鼻头小巧圆润，显得精致。
**嘴唇**：唇瓣厚度适中，唇峰明显（M唇），唇色淡粉。常态下嘴角微抿，表现出坚毅；在副本中伪装时能挤出笑容。
**发型**：黑色长直发，长度及胸，发质柔顺光泽。额前有稀疏的刘海修饰脸型（推断，符合甜美女大学生设定）。
**身材**：身材高挑，体型纤细匀称。原文描写"修长的双腿盘在电脑椅上"，说明腿部线条优美。
**特殊标记**：无特殊痣或疤痕，但在副本中右手手腕佩戴红色表带的江诗丹顿女表。
**穿着**：在第1章户外场景中身穿剪裁合体的深色长款毛呢大衣（推断为深灰或黑色，显成熟稳重），内搭米白色高领毛衣（推断）。在副本（第3-5章）中，可能仍穿着进入副本前的家居服或大衣，脚踩短靴或家居鞋。
**随身物品**：江诗丹顿女表（红色表带，贡品）、天地银行卡、贡品卡、手机（七位数余额）。
**表情习惯**：本章大部分时间表情冷静肃穆，眉心微蹙，眼神聚焦在关键信息上；面对危险人物（爸爸妈妈）时，表情切换为乖巧、虚弱或惊讶，嘴角勉强上扬。
**性格**：果断（买空所有冥币，花费巨资毫不心疼）、机智（利用双喜探路，快速分析规则矛盾）、清醒（时刻保持认知，不被虚假亲情迷惑）。
**本章心理**：极度渴望生存，同时伴有掌控局面的紧张感。原文"苏青鱼紧绷的神情，稍微放松"以及"头皮发麻"证明她在副本中时刻处于高压状态，但通过冷静分析寻找生路。
**本章变化**：从第1章现实世界中挥金如土的"疯批"准备者，转变为第3-5章惊悚副本中步步为营的"求生者"。心态从单纯的孤注一掷，转变为面对具体规则杀机时的谨慎与博弈。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务二：AI绘画提示词
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**第1组：人物标准立绘**
中文：
日系现代动画风格，16:9宽画幅。场景设定在夜晚的单身公寓内，背景是简洁的家居环境，有一张摆放着笔记本电脑的书桌，窗外是漆黑的夜色。人物苏青鱼坐在人体工学椅上，修长的双腿盘在椅子上。她身穿深灰色的长款毛呢大衣，内搭米白色宽松针织毛衣，下身是深色牛仔裤。她的一只手拿着一张泛着微弱白光的卡片（贡品卡），另一只手的手腕上戴着一只红色表带的精致女表。她的面容白皙甜美，神色却冷静肃穆，眼神正专注地审视着手中的卡片。室内灯光为冷色调的白炽灯，在人物身上投下清晰的阴影，营造出一种日常却潜藏危机的氛围。

English:
Japanese modern anime style, 16:9 aspect ratio. The scene is set in a studio apartment at night, with a simple home background featuring a desk with a laptop, and pitch-black night outside the window. The character Su Qingyu sits on an ergonomic chair, her long legs crossed on the seat. She wears a dark grey long wool coat, a beige loose knitted sweater underneath, and dark jeans. One hand holds a card glowing with faint white light (tribute card), while the other wrist wears a delicate women's watch with a red strap. Her face is fair and sweet, but her expression is calm and solemn, her eyes focused on examining the card in her hand. The indoor lighting is cool-toned incandescent light, casting clear shadows on the character, creating an atmosphere of daily life with hidden crises.
(Face Description: A young woman around 20 years old with an oval face, fair cheeks full and healthy. She has clear almond-shaped eyes, her gaze calm and witty, with deep black pupils and clear whites. Her eyebrows are pale, slender, and straight. Her nose is small and straight with a rounded tip. Her lips are moderate in thickness, pale pink, and slightly pursed. Long black hair drapes softly over her shoulders, with a few strands framing her forehead. In a modern Japanese anime style, her features are exquisite and natural; at first glance, she is a sweet college student, but upon closer inspection, there is a tough resilience between her brows.)

**第2组：面部核心段（最重要）**
中文：
一名20岁左右的年轻女性，鹅蛋脸，脸颊饱满白皙透着健康的血色。她有着一双清澈的杏眼，眼神冷静而机智，瞳孔深黑色，眼白清澈。眉毛淡雅修长，呈平直状。鼻子小巧挺拔，鼻头圆润。嘴唇适中，唇色淡粉，嘴角微微抿紧，显示出坚毅的性格。黑色长发柔顺地披散在肩头，额前有几缕稀疏的刘海修饰脸型。在日系动画风格下，她的五官精致自然，乍一看是甜美的大学生，仔细看眉宇间却有一股临危不乱的坚韧气质。

English:
A young woman around 20 years old with an oval face, fair cheeks full and healthy. She has clear almond-shaped eyes, her gaze calm and witty, with deep black pupils and clear whites. Her eyebrows are pale, slender, and straight. Her nose is small and straight with a rounded tip. Her lips are moderate in thickness, pale pink, and slightly pursed. Long black hair drapes softly over her shoulders, with a few strands framing her forehead. In a modern Japanese anime style, her features are exquisite and natural; at first glance, she is a sweet college student, but upon closer inspection, there is a tough resilience between her brows.

**第3组：关键场景**
中文：
场景位于荒凉的白石山顶，四周是光秃秃的白色巨石，地面散落着黑色的灰烬。夜晚的风吹乱了苏青鱼的长发，她站在逆风口，面前是熊熊燃烧的巨大火堆。火焰呈现出诡异的绿色光芒，照亮了她白皙的脸庞，映照出她眼中坚定的神色。她身穿深色长款大衣，双手插在口袋里，身后是堆积如山的纸扎贡品残骸。火光在风中剧烈跳动，光影在她脸上交错，形成强烈的明暗对比，画面充满了神秘与决绝的张力，暗示着某种未知仪式的完成。

English:
The scene is located on the desolate top of Baishi Mountain, surrounded by bare white giant stones, with black ashes scattered on the ground. The night wind messes up Su Qingyu's long hair. She stands with the wind at her back, facing a huge roaring fire. The flames present an eerie green glow, illuminating her fair face and reflecting the determined look in her eyes. She wears a dark long coat, hands in pockets, with debris of paper tribute offerings piled up behind her. The firelight dances violently in the wind, crossing light and shadow on her face, creating a strong contrast of light and dark, full of mystery and determination, suggesting the completion of an unknown ritual.
(Face Description: A young woman around 20 years old with an oval face, fair cheeks full and healthy. She has clear almond-shaped eyes, her gaze calm and witty, with deep black pupils and clear whites. Her eyebrows are pale, slender, and straight. Her nose is small and straight with a rounded tip. Her lips are moderate in thickness, pale pink, and slightly pursed. Long black hair drapes softly over her shoulders, with a few strands framing her forehead. In a modern Japanese anime style, her features are exquisite and natural; at first glance, she is a sweet college student, but upon closer inspection, there is a tough resilience between her brows.)

**第4组：状态变体**
中文：
分析：
- 脸色：在副本书房冷光下显得略微苍白，眼神紧绷。
- 眼神：余光警惕地瞥向身后，瞳孔微微收缩。
- 嘴部：嘴唇紧闭，抿成一条直线。
- 身体姿态：端坐在书桌前，背部僵硬挺直，双手放在键盘上假装操作，实则随时准备应对突发状况。

画面描述：
苏青鱼端坐在书房的书桌前，背对着敞开的房门。电脑屏幕发出幽幽的白光，映照在她脸上，使她的肤色看起来有些苍白。她身穿家居服，外面披着大衣，双手僵硬地放在键盘上，假装正在认真上网课。她的眼神虽然盯着屏幕，但余光充满警惕，眉头微微蹙起，嘴唇紧抿。身后的门缝里，隐约可见两个模糊的黑色人影正死死地盯着她的背影。头顶的灯光惨白，在书桌下投出浓重的阴影，空气中弥漫着一种被窥视的压抑感。

English:
Analysis:
- Face color: Looking slightly pale under the cold light of the study room, with a tense look.
- Eyes: Glancing warily towards the back from the corner of the eye, pupils slightly contracted.
- Mouth: Lips tightly closed, pressed into a line.
- Body posture: Sitting upright at the desk, back stiff and straight, hands placed on the keyboard pretending to operate, actually ready to respond to emergencies at any time.

Description:
Su Qingyu sits upright at the desk in the study, her back to the open door. The computer screen emits a faint white light, illuminating her face and making her skin look somewhat pale. She wears home clothes with a coat draped over them, her hands stiff on the keyboard, pretending to be seriously taking an online class. Although her eyes are staring at the screen, the corners of her eyes are full of alertness, her brows slightly furrowed, and her lips pursed. Through the crack of the door behind her, two blurry black figures can faintly be seen staring dead at her back. The overhead light is pale, casting heavy shadows under the desk, and the air is filled with a repressive sense of being watched.
(Face Description: A young woman around 20 years old with an oval face, fair cheeks full and healthy. She has clear almond-shaped eyes, her gaze calm and witty, with deep black pupils and clear whites. Her eyebrows are pale, slender, and straight. Her nose is small and straight with a rounded tip. Her lips are moderate in thickness, pale pink, and slightly pursed. Long black hair drapes softly over her shoulders, with a few strands framing her forehead. In a modern Japanese anime style, her features are exquisite and natural; at first glance, she is a sweet college student, but upon closer inspection, there is a tough resilience between her brows.)

**负面提示词：**
lowres, bad anatomy, bad hands, text error, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry
'''
)
API_KEY = os.getenv("TEXT2GRAPH_DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY", "")
if not API_KEY:
    raise RuntimeError("未配置 DASHSCOPE_API_KEY，请在 .env 或系统环境变量中设置")
OUTPUT_DIR = "./images"


def submit_task(prompt: str) -> str:
    """提交异步任务，返回任务ID"""
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    headers = {
        "X-DashScope-Async": "enable",
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "qwen-image-plus",
        "input": {"prompt": prompt},
        "parameters": {
            "size": "1664*928",
            "n": 1,
        },
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    result = response.json()

    task_id = result.get("output", {}).get("task_id")
    if not task_id:
        raise Exception(f"获取任务ID失败: {result}")

    return task_id


def query_task(task_id: str) -> dict:
    """查询任务状态"""
    url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def download_image(image_url: str) -> str:
    """下载图片到本地"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 从URL提取文件名
    parsed = urlparse(image_url)
    filename = os.path.basename(parsed.path)
    if not filename or "." not in filename:
        filename = f"image_{int(time.time())}.png"

    filepath = os.path.join(OUTPUT_DIR, filename)

    # 下载
    response = requests.get(image_url, stream=True)
    response.raise_for_status()

    with open(filepath, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return filepath


def main():
    print(f"提示词: {PROMPT[:100]}...")
    print("-" * 50)

    # 1. 提交任务
    print("提交任务...")
    task_id = submit_task(PROMPT)
    print(f"任务ID: {task_id}")
    print("-" * 50)

    # 2. 轮询等待（10秒间隔）
    print("等待任务完成（每10秒查询一次）...")
    max_attempts = 60  # 最多等待10分钟
    attempts = 0
    
    while attempts < max_attempts:
        time.sleep(10)
        attempts += 1
        result = query_task(task_id)
        status = result.get("output", {}).get("task_status", "UNKNOWN")
        print(f"状态: {status} (尝试 {attempts}/{max_attempts})")

        if status == "SUCCEEDED":
            break
        elif status in ("FAILED", "CANCELLED"):
            # 打印完整的错误信息
            print(f"\n任务失败详情:")
            print(f"状态: {status}")
            print(f"完整响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            raise Exception(f"任务失败: {status}")

    if attempts >= max_attempts:
        raise Exception(f"任务超时，等待了 {max_attempts * 10} 秒")

    print("-" * 50)

    # 3. 提取图片URL
    results = result.get("output", {}).get("results", [])
    image_urls = [item.get("url") for item in results if item.get("url")]

    if not image_urls:
        raise Exception("未找到图片URL")

    print(f"找到 {len(image_urls)} 个图片")

    # 4. 下载图片
    print("-" * 50)
    print("下载图片...")
    for i, url in enumerate(image_urls, 1):
        filepath = download_image(url)
        print(f"[{i}] 已保存: {filepath}")

    print("-" * 50)
    print(f"完成！图片保存在: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
