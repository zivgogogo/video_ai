#!/usr/bin/env python3
"""
OpenAI DALL-E 文生图 - 交互式版本
支持选择人物侧写MD文件、预览提示词、反馈修改、按小说分类保存图片
"""

import os
import sys
import json
import time
import requests
import re
from pathlib import Path
from urllib.parse import urlparse
import webbrowser

# 复用项目根目录的统一 .env 加载器
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env_loader import load_env

load_env()

# ========== 配置 ==========
# DashScope API Key（通义千问），从根目录 .env / 系统环境变量读取
DASHSCOPE_API_KEY = os.getenv("TEXT2GRAPH_DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY", "")
if not DASHSCOPE_API_KEY:
    raise RuntimeError("未配置 DASHSCOPE_API_KEY，请在 .env 或系统环境变量中设置")

OUTPUT_BASE_DIR = r"E:\Qoder\picture"


# ========== 工具函数 ==========
def list_md_files(directory):
    """列出指定目录下的人物侧写MD文件"""
    if not os.path.exists(directory):
        print(f"未找到文件夹: {directory}")
        return []
    
    md_files = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.endswith('.md') and 'character' in f.lower():
                filepath = os.path.join(root, f)
                md_files.append(filepath)
    
    if not md_files:
        print("未找到人物侧写MD文件")
        return []
    
    print("\n可用的人物侧写MD文件:")
    for i, f in enumerate(md_files, 1):
        # 从路径中提取小说文件夹名
        rel_path = os.path.relpath(f, directory)
        parts = rel_path.split(os.sep)
        novel_name = parts[0] if len(parts) > 1 else "未知小说"
        print(f"  {i}. [{novel_name}] {os.path.basename(f)}")
    
    return md_files


def extract_image_prompts(md_content):
    """从人物侧写MD内容中提取AI绘画提示词"""
    prompts = []
    
    # 优先匹配格式：## 第1组 或 **第1组** 或 第1组：
    group_patterns = [
        r'## 第(\d+)组[：:]\s*(.*?)(?=## 第\d+组|$)',
        r'\*\*第(\d+)组[：:].*?\*\*\s*(.*?)(?=\*\*第\d+组|$)',
        r'第(\d+)组[：:]\s*(.*?)(?=第\d+组[：:]|$)',
    ]
    
    groups = []
    for pattern in group_patterns:
        groups = re.findall(pattern, md_content, re.DOTALL)
        if groups:
            break
    
    if groups:
        group_names = {
            "1": "人物正面半身像",
            "2": "关键场景",
            "3": "状态变体",
            "4": "面部核心段"
        }
        
        for num, content in groups:
            # 提取中文部分
            cn_match = re.search(r'中文[：:]\s*(.*?)(?=English[：:])', content, re.DOTALL)
            # 提取英文部分
            en_match = re.search(r'English[：:]\s*(.*)', content, re.DOTALL)
            
            cn_prompt = cn_match.group(1).strip() if cn_match else ""
            en_prompt = en_match.group(1).strip() if en_match else ""
            
            name = group_names.get(num, f"第{num}组")
            prompts.append({
                "name": name,
                "chinese": cn_prompt,
                "english": en_prompt
            })
        
        return prompts
    
    # 备用：直接匹配所有"中文："和"English："
    cn_prompts = re.findall(r'中文[：:]\s*(.*?)(?=English[：:]|$)', md_content, re.DOTALL)
    en_prompts = re.findall(r'English[：:]\s*(.*?)(?=(?:中文|第\d+组)|$)', md_content, re.DOTALL)
    
    group_names = ["人物正面半身像", "关键场景"]
    for i, (cn, en) in enumerate(zip(cn_prompts, en_prompts)):
        prompts.append({
            "name": group_names[i] if i < len(group_names) else f"第{i+1}组",
            "chinese": cn.strip(),
            "english": en.strip()
        })
    
    return prompts


def extract_novel_name_from_path(filepath):
    """从MD文件路径中提取小说名称"""
    # 路径格式: E:\QoderWork\outputs\character_profiles\[小说名称]\character_XXX.md
    rel_path = os.path.relpath(filepath, r"E:\QoderWork\outputs\character_profiles")
    parts = rel_path.split(os.sep)
    if len(parts) > 1:
        return parts[0]
    return "未知小说"


def analyze_prompts_with_ai(prompts, md_content):
    """调用AI分析提示词组，给出专业建议、进阶提示和动态组数检测"""
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}"
    }
    
    # 动态构建分析请求，根据实际组数
    prompt_summary = f"你是一个专业的AI绘画提示词优化师。MD文件中共有{len(prompts)}组AI绘画提示词，请逐一分析：\n\n"
    prompt_summary += "1. **人物核心特征浓缩**：用3-5句话总结人物的外貌特征、气质、穿着风格\n"
    prompt_summary += f"2. **每组提示词的专业评价**（共{len(prompts)}组）：指出每组的优点和可优化点\n"
    prompt_summary += "3. **整体优化建议**：给出整体优化方向\n"
    prompt_summary += "4. **推荐生成顺序**：建议优先跑哪几张，为什么\n"
    prompt_summary += "5. **进阶生成建议**：提供2-3条具体的、可操作的进阶优化建议（如：光线调整、风格转换、构图建议等）\n\n"
    
    for i, p in enumerate(prompts, 1):
        prompt_summary += f"**第{i}组 {p['name']}**:\n"
        prompt_summary += f"中文: {p['chinese'][:300]}...\n\n"
    
    prompt_summary += "\n请以清晰的格式输出分析结果，并在最后以【进阶建议】开头，给出2-3条具体可操作的生成优化建议。"
    
    payload = {
        "model": "qwen-plus",
        "messages": [
            {"role": "system", "content": "你是专业的AI绘画提示词分析师，擅长优化人物立绘和场景提示词。"},
            {"role": "user", "content": prompt_summary}
        ],
        "enable_thinking": False
    }
    
    print("\n正在AI分析提示词，请稍候...")
    print("-" * 50)
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            analysis = result["choices"][0].get("message", {}).get("content", "")
            return analysis
        return "AI分析失败，使用原始提示词。"
    except Exception as e:
        return f"AI分析出错: {str(e)}，使用原始提示词。"


# ========== DashScope 通义千问文生图 API 调用 ==========
def call_qwen_image(prompt: str, size: str = "16:9") -> str:
    """
    调用 DashScope 通义千问文生图 API
    返回图片保存路径
    """
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    
    headers = {
        "X-DashScope-Async": "enable",
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # 尺寸映射（wanx-v1 支持的尺寸）
    size_map = {
        "16:9": "1280*720",
        "1:1": "1024*1024",
        "9:16": "720*1280",
    }
    actual_size = size_map.get(size, size)
    
    payload = {
        "model": "wanx-v1",
        "input": {
            "prompt": prompt,
        },
        "parameters": {
            "size": actual_size,
            "n": 1,
        },
    }
    
    print(f"\n正在提交通义千问图片生成任务...")
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    
    result = response.json()
    task_id = result.get("output", {}).get("task_id")
    if not task_id:
        raise Exception(f"获取任务ID失败: {result}")
    
    print(f"任务ID: {task_id}")
    
    # 轮询等待任务完成
    return wait_for_qwen_task(task_id)


def wait_for_qwen_task(task_id: str, max_attempts: int = 60) -> str:
    """等待通义千问任务完成"""
    url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}
    
    print(f"\n等待任务完成（每10秒查询一次）...")
    attempts = 0
    
    while attempts < max_attempts:
        time.sleep(10)
        attempts += 1
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()
        
        status = result.get("output", {}).get("task_status", "UNKNOWN")
        print(f"状态: {status} (尝试 {attempts}/{max_attempts})")
        
        if status == "SUCCEEDED":
            results = result.get("output", {}).get("results", [])
            if results and results[0].get("url"):
                return download_image(results[0]["url"])
            raise Exception("未找到图片URL")
        elif status in ("FAILED", "CANCELLED"):
            raise Exception(f"任务失败: {result}")
    
    raise Exception(f"任务超时")


def download_image(image_url: str) -> str:
    """下载图片到本地"""
    timestamp = int(time.time())
    filename = f"qwen_{timestamp}.png"
    
    # 临时下载路径
    temp_dir = os.path.join(OUTPUT_BASE_DIR, "_temp")
    os.makedirs(temp_dir, exist_ok=True)
    filepath = os.path.join(temp_dir, filename)
    
    print(f"正在下载图片...")
    response = requests.get(image_url, stream=True, timeout=60)
    response.raise_for_status()
    
    with open(filepath, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    return filepath


def save_image_to_category(filepath: str, novel_name: str, prompt_name: str, character_name: str = "", chapter_str: str = "") -> str:
    """将图片移动到按小说分类的文件夹，按人物名+章节号命名"""
    # 目标路径
    novel_dir = os.path.join(OUTPUT_BASE_DIR, novel_name)
    os.makedirs(novel_dir, exist_ok=True)
    
    # 新文件名：人物名_ch章节号_提示词组名_时间戳.png
    timestamp = int(time.time())
    safe_name = re.sub(r'[^\w\s-]', '', prompt_name)
    
    # 构建文件名
    name_parts = []
    if character_name:
        name_parts.append(character_name)
    if chapter_str:
        name_parts.append(f"ch{chapter_str}")
    name_parts.append(safe_name)
    name_parts.append(str(timestamp))
    
    new_filename = "_".join(name_parts) + ".png"
    new_filepath = os.path.join(novel_dir, new_filename)
    
    # 移动文件
    import shutil
    shutil.move(filepath, new_filepath)
    
    return new_filepath


# ========== 交互流程 ==========
def preview_prompt(prompt_data):
    """预览提示词"""
    print("\n" + "="*60)
    print("【提示词预览】")
    print("="*60)
    print(f"组名: {prompt_data['name']}")
    print(f"\n中文:")
    print(prompt_data['chinese'][:200] + "..." if len(prompt_data['chinese']) > 200 else prompt_data['chinese'])
    print(f"\nEnglish:")
    print(prompt_data['english'][:200] + "..." if len(prompt_data['english']) > 200 else prompt_data['english'])
    print("="*60)


def list_novel_folders(directory):
    """列出指定目录下按小说分类的子文件夹"""
    if not os.path.exists(directory):
        print(f"未找到文件夹: {directory}")
        return []
    
    folders = [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]
    
    if not folders:
        print("未找到小说文件夹")
        return []
    
    print("\n可用的小说文件夹:")
    for i, f in enumerate(folders, 1):
        # 统计每个文件夹里的MD文件数
        md_count = len([x for x in os.listdir(os.path.join(directory, f)) if x.endswith('.md')])
        print(f"  {i}. {f} ({md_count}个文件)")
    
    return folders


def list_md_files_in_folder(directory, folder_name):
    """列出指定小说文件夹下的所有人物侧写MD文件"""
    folder_path = os.path.join(directory, folder_name)
    if not os.path.exists(folder_path):
        print(f"未找到文件夹: {folder_name}")
        return []
    
    md_files = [f for f in os.listdir(folder_path) if f.endswith('.md') and 'character' in f.lower()]
    
    if not md_files:
        print("未找到人物侧写MD文件")
        return []
    
    print(f"\n【{folder_name}】下的人物侧写文件:")
    for i, f in enumerate(md_files, 1):
        print(f"  {i}. {f}")
    
    return md_files


def main():
    print("="*60)
    print("通义千问文生图 - 交互式版本")
    print("="*60)
    
    if DASHSCOPE_API_KEY == "sk-YOUR_DASHSCOPE_API_KEY_HERE":
        print("\n警告: 请先在脚本中配置 DashScope API Key")
        print("注册地址: https://dashscope.console.aliyun.com/")
        return
    
    # 1. 选择小说文件夹
    md_base_dir = r"E:\QoderWork\outputs\character_profiles"
    novel_folders = list_novel_folders(md_base_dir)
    if not novel_folders:
        return
    
    print("\n请选择小说文件夹（输入序号）:")
    while True:
        choice = input("请输入: ").strip()
        try:
            idx = int(choice)
            if 1 <= idx <= len(novel_folders):
                selected_novel = novel_folders[idx-1]
                break
            else:
                print("序号超出范围，请重新输入")
        except:
            print("格式错误，请输入数字")
    
    # 2. 选择人物侧写MD文件
    md_files = list_md_files_in_folder(md_base_dir, selected_novel)
    if not md_files:
        return
    
    print("\n请选择人物侧写文件（输入序号）:")
    while True:
        choice = input("请输入: ").strip()
        try:
            idx = int(choice)
            if 1 <= idx <= len(md_files):
                selected_file = os.path.join(md_base_dir, selected_novel, md_files[idx-1])
                break
            else:
                print("序号超出范围，请重新输入")
        except:
            print("格式错误，请输入数字")
    
    # 读取MD文件内容
    with open(selected_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # 从文件名提取人物名和章节号
    # 文件名格式: character_苏青鱼_规则怪谈，欢迎来到甜蜜的家_弦_ch1-2-3-4-5_20260423.md
    md_filename = os.path.basename(selected_file)
    character_name = ""
    chapter_str = ""
    
    # 提取人物名：character_XXX_ 之间的部分
    char_match = re.search(r'character_(.+?)_', md_filename)
    if char_match:
        character_name = char_match.group(1)
        # 如果人物名里还包含小说名，截取第一个下划线前的部分
        if '_' in character_name:
            character_name = character_name.split('_')[0]
    
    # 提取章节号：chXXX_ 之间的部分
    chap_match = re.search(r'ch([\d-]+)_', md_filename)
    if chap_match:
        chapter_str = chap_match.group(1)
    
    # 小说名称直接用选择的文件夹名
    novel_name = selected_novel
    
    print(f"\n已选择文件: {md_filename}")
    print(f"人物: {character_name}" if character_name else "")
    print(f"章节: ch{chapter_str}" if chapter_str else "")
    
    # 提取提示词
    prompts = extract_image_prompts(md_content)
    if not prompts:
        print("未能从文件中提取到AI绘画提示词")
        return
    
    print(f"\n已选择文件: {os.path.basename(selected_file)}")
    print(f"小说: {novel_name}")
    print(f"找到 {len(prompts)} 组提示词")
    
    # 2. AI分析提示词并给出专业建议
    print("\n" + "="*60)
    print("【AI 提示词分析报告】")
    print("="*60)
    analysis = analyze_prompts_with_ai(prompts, md_content)
    print(analysis)
    print("="*60)
    
    # 3. 预览每组提示词并让用户选择
    num_groups = len(prompts)
    print(f"\nMD文件中共有 {num_groups} 组提示词，请选择运行方式:")
    print("-"*60)
    for i, p in enumerate(prompts, 1):
        print(f"  {i}. {p['name']}")
    print(f"  f. 融合全部{num_groups}组提示词生成一张综合人物图")
    print(f"  all. 分别生成全部{num_groups}组")
    print("-"*60)
    print("运行方式说明:")
    print("  单一运行: 输入单个序号，如 1")
    print("  组合运行: 输入多个序号用逗号分隔，如 1,3")
    print("  全部运行: 输入 all")
    print("  融合运行: 输入 f")
    
    while True:
        choice = input("请输入序号或选项: ").strip().lower()
        if choice == 'f':
            # 融合模式：生成一张综合图
            selected_prompts = prompts  # 全部用于融合
            fusion_mode = True
            break
        elif choice == 'all':
            selected_prompts = prompts
            fusion_mode = False
            break
        try:
            indices = [int(x.strip()) for x in choice.split(',')]
            selected_prompts = [prompts[i-1] for i in indices if 1 <= i <= len(prompts)]
            fusion_mode = False
            if selected_prompts:
                break
            else:
                print("序号超出范围，请重新输入")
        except:
            print("格式错误，请重新输入")
    
    # 4. 选择图片尺寸
    print("\n请选择图片尺寸:")
    print("1. 16:9 横版（默认）")
    print("2. 1:1 正方形")
    print("3. 9:16 竖版")
    size_choice = input("请输入 (1-3): ").strip()
    size_map = {"1": "16:9", "2": "1:1", "3": "9:16"}
    selected_size = size_map.get(size_choice, "16:9")
    
    # 融合模式处理
    fusion_prompt_data = None
    if fusion_mode and len(prompts) >= 2:
        print("\n" + "="*60)
        print(f"【融合模式】将{len(prompts)}组提示词融合生成一张综合人物图")
        print("="*60)
        # 构建融合prompt：根据实际组数动态融合
        # 第1组通常是全身/人物正面
        personality = prompts[0]['chinese'] if len(prompts) > 0 else ""
        # 第2组通常是面部核心/关键场景
        face_core = prompts[1]['chinese'] if len(prompts) > 1 else ""
        # 后续组是场景、状态等
        scene = prompts[2]['chinese'] if len(prompts) > 2 else ""
        state = prompts[3]['chinese'] if len(prompts) > 3 else ""
        
        # 提取关键元素融合
        fusion_cn = f"(masterpiece, best quality, ultra-detailed, highly detailed:1.2), sharp focus, clear image, 8k resolution, "
        # 从面部核心段提取五官描写
        face_desc = re.search(r'(鹅蛋脸|瓜子脸|圆润|白皙|杏眼|双眼皮|鼻梁|嘴唇|唇形|淡粉|自然眉|柳叶眉|深棕色|黑色.*?发)', face_core)
        if face_desc:
            fusion_cn += face_desc.group(0) + "，"
        # 添加气质和场景
        fusion_cn += "正面朝向镜头，全身或半身像，"
        fusion_cn += scene[:100] if scene else ""
        fusion_cn += state[:80] if state else ""
        
        # 英文融合
        fusion_en = f"(masterpiece, best quality, ultra-detailed, highly detailed:1.2), sharp focus, clear image, 8k resolution, "
        face_en = prompts[1]['english'] if len(prompts) > 1 else ""
        fusion_en += face_en[:200] if face_en else ""
        fusion_en += ", full body or bust shot, facing camera directly, "
        scene_en = prompts[2]['english'] if len(prompts) > 2 else ""
        fusion_en += scene_en[:150] if scene_en else ""
        
        fusion_prompt_data = {
            "name": "融合综合人物图",
            "chinese": fusion_cn,
            "english": fusion_en
        }
        
        print(f"\n融合后的提示词:")
        print(f"中文: {fusion_cn[:200]}...")
        print(f"English: {fusion_en[:200]}...")
        
        confirm = input("\n是否使用融合提示词生成？(y/n): ").strip().lower()
        if confirm != 'y':
            fusion_mode = False
            fusion_prompt_data = None
        else:
            selected_prompts = [fusion_prompt_data]
    
    # 5. 逐组生成、预览、确认保存
    generated_images = []
    
    for prompt_data in selected_prompts:
        print("\n" + "="*60)
        print(f"准备生成: {prompt_data['name']}")
        preview_prompt(prompt_data)
        
        # 确认是否生成这张
        confirm = input("\n是否生成这张图片？(y/n): ").strip().lower()
        if confirm != 'y':
            print(f"已跳过: {prompt_data['name']}")
            continue
        
        # 生成 → 预览 → 确认保存 循环
        while True:
            try:
                # 生成图片
                image_prompt = prompt_data['english'] if prompt_data['english'] else prompt_data['chinese']
                image_path = call_qwen_image(image_prompt, selected_size)
                
                # 打开预览
                print(f"\n图片已下载到: {image_path}")
                try:
                    os.startfile(image_path)
                except:
                    webbrowser.open(f'file://{os.path.abspath(image_path)}')
                
                # 用户确认
                print("\n请预览图片后选择:")
                print("1. 满意，保存")
                print("2. 不满意，添加补充提示词后重新生成")
                print("3. 不满意，不添加提示词直接重新生成")
                print("4. 跳过此项，不保存")
                choice = input("请输入 (1/2/3/4): ").strip()
                
                if choice == '1':
                    # 保存
                    saved_path = save_image_to_category(image_path, novel_name, prompt_data['name'], character_name, chapter_str)
                    generated_images.append(saved_path)
                    print(f"图片已保存到: {saved_path}")
                    break
                    
                elif choice == '2':
                    # 添加补充提示词
                    print("\n请输入要补充的提示词（如：更亮一些、增加氛围感 等，输入空行跳过）:")
                    extra = input("补充: ").strip()
                    if extra:
                        # 追加到英文prompt末尾
                        if prompt_data['english']:
                            prompt_data['english'] = prompt_data['english'].rstrip('.') + ', ' + extra
                        else:
                            prompt_data['english'] = extra
                        print(f"已追加: {extra}")
                    print("\n使用新提示词重新生成...")
                    # 删除临时文件
                    try:
                        os.remove(image_path)
                    except:
                        pass
                    continue
                    
                elif choice == '3':
                    # 不添加提示词，直接重新生成
                    print("\n重新生成中...")
                    try:
                        os.remove(image_path)
                    except:
                        pass
                    continue
                    
                elif choice == '4':
                    # 跳过
                    print(f"已跳过: {prompt_data['name']}")
                    try:
                        os.remove(image_path)
                    except:
                        pass
                    break
                    
            except Exception as e:
                print(f"\n生成失败: {e}")
                retry = input("是否重试？(y/n): ").strip().lower()
                if retry != 'y':
                    break
    
    # 6. 完成
    print("\n" + "="*60)
    print("生成完成！")
    print(f"共生成 {len(generated_images)} 张图片")
    print(f"保存位置: {os.path.join(OUTPUT_BASE_DIR, novel_name)}")
    for img in generated_images:
        print(f"  - {os.path.basename(img)}")
    print("="*60)


if __name__ == "__main__":
    main()
