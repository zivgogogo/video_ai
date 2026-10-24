#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试视频下载脚本
从角色一致性测试进度文件中下载所有生成的视频
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime


def download_video(url, save_path, timeout=300):
    """
    下载单个视频文件
    
    Args:
        url: 视频URL
        save_path: 保存路径
        timeout: 超时时间（秒）
    
    Returns:
        bool: 是否成功
    """
    try:
        print(f"  ⬇️  下载中...")
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()
        
        # 获取文件大小
        total_size = int(response.headers.get('content-length', 0))
        
        # 写入文件
        with open(save_path, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    # 显示进度
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        print(f"  📥 {progress:.1f}%", end='\r')
        
        print(f"  ✅ 下载完成: {save_path}")
        return True
        
    except Exception as e:
        print(f"  ❌ 下载失败: {str(e)}")
        return False


def load_test_progress(progress_file):
    """
    加载测试进度文件
    
    Args:
        progress_file: 进度文件路径
    
    Returns:
        dict: 测试进度数据
    """
    with open(progress_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def download_all_videos(progress_file, output_dir="test_videos"):
    """
    下载所有测试视频
    
    Args:
        progress_file: 测试进度文件路径
        output_dir: 输出目录
    """
    print("\n" + "="*80)
    print("📥 测试视频下载工具")
    print("="*80)
    
    # 加载进度
    print(f"\n📂 加载进度文件: {progress_file}")
    progress = load_test_progress(progress_file)
    
    # 创建输出目录
    base_dir = Path(output_dir)
    base_dir.mkdir(exist_ok=True)
    
    group_a_dir = base_dir / "A组_有角色一致性"
    group_b_dir = base_dir / "B组_无角色一致性"
    group_a_dir.mkdir(exist_ok=True)
    group_b_dir.mkdir(exist_ok=True)
    
    # 统计
    total_downloaded = 0
    total_failed = 0
    
    # 下载A组视频
    group_a = progress.get('group_a_with_consistency', [])
    if group_a:
        print(f"\n🎬 A组视频（有角色一致性）: {len(group_a)} 个")
        print("-" * 80)
        
        for i, result in enumerate(group_a, 1):
            if result.get('status') == 'success':
                video_url = result.get('video_url', '')
                shot_num = result.get('shot_number', i)
                scene = result.get('scene', f'分镜{shot_num}')
                
                # 清理文件名
                safe_scene = scene.replace(' - ', '_').replace(' ', '_')
                filename = f"shot{shot_num:02d}_{safe_scene}.mp4"
                save_path = group_a_dir / filename
                
                print(f"\n[{i}/{len(group_a)}] {scene}")
                print(f"  文件: {filename}")
                
                if download_video(video_url, str(save_path)):
                    total_downloaded += 1
                else:
                    total_failed += 1
            else:
                print(f"\n[{i}/{len(group_a)}] 跳过（状态: {result.get('status')}）")
    
    # 下载B组视频
    group_b = progress.get('group_b_without_consistency', [])
    if group_b:
        print(f"\n🎬 B组视频（无角色一致性）: {len(group_b)} 个")
        print("-" * 80)
        
        for i, result in enumerate(group_b, 1):
            if result.get('status') == 'success':
                video_url = result.get('video_url', '')
                shot_num = result.get('shot_number', i)
                scene = result.get('scene', f'分镜{shot_num}')
                
                # 清理文件名
                safe_scene = scene.replace(' - ', '_').replace(' ', '_')
                filename = f"shot{shot_num:02d}_{safe_scene}.mp4"
                save_path = group_b_dir / filename
                
                print(f"\n[{i}/{len(group_b)}] {scene}")
                print(f"  文件: {filename}")
                
                if download_video(video_url, str(save_path)):
                    total_downloaded += 1
                else:
                    total_failed += 1
            else:
                print(f"\n[{i}/{len(group_b)}] 跳过（状态: {result.get('status')}）")
    
    # 生成下载清单
    manifest = {
        'download_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source_file': progress_file,
        'output_dir': output_dir,
        'statistics': {
            'total_downloaded': total_downloaded,
            'total_failed': total_failed,
            'group_a_count': len([r for r in group_a if r.get('status') == 'success']),
            'group_b_count': len([r for r in group_b if r.get('status') == 'success'])
        },
        'files': {
            'group_a': [str(group_a_dir / f"shot{r.get('shot_number', i):02d}_{r.get('scene', '').replace(' - ', '_').replace(' ', '_')}.mp4") 
                       for i, r in enumerate(group_a) if r.get('status') == 'success'],
            'group_b': [str(group_b_dir / f"shot{r.get('shot_number', i):02d}_{r.get('scene', '').replace(' - ', '_').replace(' ', '_')}.mp4") 
                       for i, r in enumerate(group_b) if r.get('status') == 'success']
        }
    }
    
    manifest_file = base_dir / "download_manifest.json"
    with open(manifest_file, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    # 打印总结
    print("\n" + "="*80)
    print("📊 下载总结")
    print("="*80)
    print(f"✅ 成功下载: {total_downloaded} 个视频")
    print(f"❌ 失败: {total_failed} 个")
    print(f"\n📁 保存位置: {base_dir.absolute()}")
    print(f"📋 下载清单: {manifest_file}")
    
    print(f"\n🎬 下一步:")
    print(f"  1. 打开文件夹: {base_dir.absolute()}")
    print(f"  2. 用剪映导入A组和B组视频")
    print(f"  3. 对比角色一致性效果")
    
    return manifest


def find_latest_progress():
    """
    查找最新的测试进度文件
    
    Returns:
        str: 进度文件路径
    """
    progress_files = list(Path('.').glob('test_progress_*.json'))
    
    if not progress_files:
        return None
    
    # 按修改时间排序
    latest = max(progress_files, key=lambda p: p.stat().st_mtime)
    return str(latest)


def download_group_only(progress_file, group_name):
    """
    只下载指定组的视频
    
    Args:
        progress_file: 进度文件路径
        group_name: 'A' 或 'B'
    """
    progress = load_test_progress(progress_file)
    
    base_dir = Path('test_videos')
    base_dir.mkdir(exist_ok=True)
    
    if group_name == 'A':
        group_dir = base_dir / "A组_有角色一致性"
        videos = progress.get('group_a_with_consistency', [])
    else:
        group_dir = base_dir / "B组_无角色一致性"
        videos = progress.get('group_b_without_consistency', [])
    
    group_dir.mkdir(exist_ok=True)
    
    downloaded = 0
    for i, result in enumerate(videos, 1):
        if result.get('status') == 'success':
            video_url = result.get('video_url', '')
            shot_num = result.get('shot_number', i)
            scene = result.get('scene', f'分镜{shot_num}')
            
            safe_scene = scene.replace(' - ', '_').replace(' ', '_')
            filename = f"shot{shot_num:02d}_{safe_scene}.mp4"
            save_path = group_dir / filename
            
            print(f"\n[{i}/{len(videos)}] {scene}")
            if download_video(video_url, str(save_path)):
                downloaded += 1
    
    print(f"\n✅ 完成！下载了 {downloaded} 个视频到: {group_dir}")


def download_selected_videos(progress_file, selected_indices):
    """
    下载指定的视频
    
    Args:
        progress_file: 进度文件路径
        selected_indices: 要下载的视频编号列表
    """
    progress = load_test_progress(progress_file)
    
    # 合并所有视频
    all_videos = []
    for r in progress.get('group_a_with_consistency', []):
        all_videos.append(('A', r))
    for r in progress.get('group_b_without_consistency', []):
        all_videos.append(('B', r))
    
    base_dir = Path('test_videos')
    base_dir.mkdir(exist_ok=True)
    
    downloaded = 0
    for idx in selected_indices:
        if 1 <= idx <= len(all_videos):
            group, result = all_videos[idx - 1]
            
            if result.get('status') == 'success':
                video_url = result.get('video_url', '')
                shot_num = result.get('shot_number', idx)
                scene = result.get('scene', f'分镜{shot_num}')
                
                if group == 'A':
                    group_dir = base_dir / "A组_有角色一致性"
                else:
                    group_dir = base_dir / "B组_无角色一致性"
                
                group_dir.mkdir(exist_ok=True)
                
                safe_scene = scene.replace(' - ', '_').replace(' ', '_')
                filename = f"shot{shot_num:02d}_{safe_scene}.mp4"
                save_path = group_dir / filename
                
                print(f"\n下载 [{idx}] {scene}")
                if download_video(video_url, str(save_path)):
                    downloaded += 1
            else:
                print(f"\n跳过 [{idx}] (状态: {result.get('status')})")
        else:
            print(f"\n❌ 编号 {idx} 超出范围")
    
    print(f"\n✅ 完成！下载了 {downloaded} 个视频")


def download_latest_only(progress_file):
    """
    只下载最新的一个视频
    
    Args:
        progress_file: 进度文件路径
    """
    progress = load_test_progress(progress_file)
    
    # 优先B组，其次A组
    group_b = progress.get('group_b_without_consistency', [])
    group_a = progress.get('group_a_with_consistency', [])
    
    latest_video = None
    group_name = None
    
    # 查找最新的成功视频
    for r in reversed(group_b):
        if r.get('status') == 'success':
            latest_video = r
            group_name = 'B'
            break
    
    if not latest_video:
        for r in reversed(group_a):
            if r.get('status') == 'success':
                latest_video = r
                group_name = 'A'
                break
    
    if not latest_video:
        print("❌ 没有可下载的视频")
        return
    
    base_dir = Path('test_videos')
    base_dir.mkdir(exist_ok=True)
    
    if group_name == 'A':
        group_dir = base_dir / "A组_有角色一致性"
    else:
        group_dir = base_dir / "B组_无角色一致性"
    
    group_dir.mkdir(exist_ok=True)
    
    video_url = latest_video.get('video_url', '')
    shot_num = latest_video.get('shot_number', 1)
    scene = latest_video.get('scene', f'分镜{shot_num}')
    
    safe_scene = scene.replace(' - ', '_').replace(' ', '_')
    filename = f"shot{shot_num:02d}_{safe_scene}.mp4"
    save_path = group_dir / filename
    
    print(f"\n📥 下载最新视频: {scene}")
    if download_video(video_url, str(save_path)):
        print(f"\n✅ 已保存到: {save_path}")


def main():
    """主函数"""
    print("\n" + "="*80)
    print("🎬 角色一致性测试视频下载器")
    print("="*80)
    
    # 查找最新的进度文件
    progress_file = find_latest_progress()
    
    if not progress_file:
        print("\n❌ 未找到测试进度文件")
        print("请先运行: python run_consistency_comparison.py")
        return
    
    print(f"\n✓ 找到进度文件: {progress_file}")
    
    # 加载进度查看有哪些视频
    progress = load_test_progress(progress_file)
    group_a = progress.get('group_a_with_consistency', [])
    group_b = progress.get('group_b_without_consistency', [])
    
    print(f"\n📊 可用视频:")
    print(f"  A组（有角色一致性）: {len(group_a)} 个")
    for i, r in enumerate(group_a, 1):
        if r.get('status') == 'success':
            print(f"    [{i}] {r.get('scene', '分镜' + str(r.get('shot_number', i)))}")
    
    print(f"  B组（无角色一致性）: {len(group_b)} 个")
    for i, r in enumerate(group_b, 1):
        if r.get('status') == 'success':
            print(f"    [{len(group_a)+i}] {r.get('scene', '分镜' + str(r.get('shot_number', i)))}")
    
    # 让用户选择下载方式
    print(f"\n📥 下载选项:")
    print(f"  [1] 下载全部视频")
    print(f"  [2] 只下载A组（有角色一致性）")
    print(f"  [3] 只下载B组（无角色一致性）")
    print(f"  [4] 选择下载指定视频")
    print(f"  [5] 只下载最新的一个视频")
    
    choice = input("\n请选择 (1-5): ").strip()
    
    if choice == '1':
        # 下载全部
        print(f"\n📥 将下载所有 {len(group_a) + len(group_b)} 个视频")
        confirm = input("确认？(y/n): ").strip().lower()
        if confirm == 'y':
            download_all_videos(progress_file)
    
    elif choice == '2':
        # 只下载A组
        print(f"\n📥 将下载A组 {len(group_a)} 个视频")
        confirm = input("确认？(y/n): ").strip().lower()
        if confirm == 'y':
            download_group_only(progress_file, 'A')
    
    elif choice == '3':
        # 只下载B组
        print(f"\n📥 将下载B组 {len(group_b)} 个视频")
        confirm = input("确认？(y/n): ").strip().lower()
        if confirm == 'y':
            download_group_only(progress_file, 'B')
    
    elif choice == '4':
        # 选择下载
        print(f"\n请输入要下载的视频编号（多个用逗号分隔）")
        indices = input("编号: ").strip()
        try:
            selected = [int(x.strip()) for x in indices.split(',')]
            download_selected_videos(progress_file, selected)
        except:
            print("❌ 输入格式错误")
    
    elif choice == '5':
        # 只下载最新的一个
        print(f"\n📥 将下载最新生成的视频")
        confirm = input("确认？(y/n): ").strip().lower()
        if confirm == 'y':
            download_latest_only(progress_file)
    
    else:
        print("❌ 无效选择")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  下载已取消")
    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
