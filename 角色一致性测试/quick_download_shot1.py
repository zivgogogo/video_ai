#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速下载视频1 - 咖啡店场景
"""

import json
import requests
from pathlib import Path

def download_video(url, save_path):
    """下载视频"""
    print(f"⬇️  下载中...")
    response = requests.get(url, timeout=300, stream=True)
    response.raise_for_status()
    
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    
    print(f"✅ 下载完成: {save_path}")

# 加载进度文件
with open('test_progress_20260519_205247.json', 'r', encoding='utf-8') as f:
    progress = json.load(f)

# 获取第一个视频
video = progress['group_a_with_consistency'][0]
video_url = video['video_url']

# 创建目录
save_dir = Path('test_videos/A组_有角色一致性')
save_dir.mkdir(parents=True, exist_ok=True)

# 下载
save_path = save_dir / 'shot01_咖啡店_白天.mp4'
print(f"\n📥 下载视频: {video['scene']}")
download_video(video_url, str(save_path))
print(f"\n✅ 完成！")
