#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
角色一致性实际对比测试脚本

测试方案：
1. 使用同样的分镜脚本
2. A组：启用角色一致性生成视频
3. B组：不启用角色一致性生成视频
4. 对比两组视频的角色外观一致性

注意：此脚本会实际调用API生成视频，需要有效的API Key
"""

import os
import sys
import json
import time
import requests
from typing import Dict, List, Optional
from datetime import datetime

# 复用项目根目录的统一 .env 加载器，API Key 只从 .env / 环境变量读取
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from env_loader import load_env

load_env()


class ConsistencyComparisonTest:
    """角色一致性对比测试"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get('DASHSCOPE_API_KEY')
        if not self.api_key:
            raise ValueError("❌ 未找到API Key，请设置环境变量 DASHSCOPE_API_KEY")
        
        self.api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
        self.results = {
            'group_a_with_consistency': [],
            'group_b_without_consistency': [],
            'test_metadata': {}
        }
    
    def load_storyboard(self, file_path: str) -> Dict:
        """加载测试分镜脚本"""
        print(f"\n📂 加载测试分镜: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            storyboard = json.load(f)
        
        print(f"✓ 标题: {storyboard.get('title')}")
        print(f"✓ 分镜数: {len(storyboard.get('shots', []))}")
        print(f"✓ 测试角色: {storyboard.get('characters_to_test', [{}])[0].get('name')}")
        
        return storyboard
    
    def generate_character_reference(self, character_name: str) -> str:
        """
        生成角色参考描述（模拟用户提供参考）
        实际应用中，这里可以是用户上传的参考图URL
        """
        reference = f"""A 25-year-old East Asian woman named {character_name}:
- Face: Delicate oval face shape, fair skin, large almond-shaped dark brown eyes, small straight nose, soft pink lips
- Hair: Long straight black hair reaching to mid-back, natural shine
- Body: Slim figure, approximately 165cm tall, graceful posture
- Distinguishing features: Small beauty mark under left eye, gentle smile
- Style: Adapts clothing to different scenarios but maintains same facial features and hairstyle"""
        
        return reference
    
    def create_video_task_with_consistency(self, prompt: str, duration: int, 
                                          character_ref: str) -> str:
        """创建带角色一致性的视频任务"""
        headers = {
            'X-DashScope-Async': 'enable',
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # 增强prompt，加入角色参考
        enhanced_prompt = f"{prompt}\n\nCharacter Reference: {character_ref}"
        
        data = {
            "model": "kling/kling-v3-omni-video-generation",
            "input": {
                "prompt": enhanced_prompt,
                "multi_shot": False
            },
            "parameters": {
                "mode": "pro",
                "aspect_ratio": "16:9",
                "duration": duration,
                "audio": False,
                "watermark": False
            }
        }
        
        response = requests.post(self.api_url, headers=headers, json=data)
        result = response.json()
        
        if response.status_code == 200 and 'output' in result:
            task_id = result['output'].get('task_id')
            return task_id
        else:
            error_msg = result.get('message', 'Unknown error')
            raise RuntimeError(f"任务创建失败: {error_msg}")
    
    def create_video_task_without_consistency(self, prompt: str, duration: int) -> str:
        """创建不带角色一致性的视频任务（对照组）"""
        headers = {
            'X-DashScope-Async': 'enable',
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            "model": "kling/kling-v3-video-generation",
            "input": {
                "prompt": prompt,
                "multi_shot": False
            },
            "parameters": {
                "mode": "pro",
                "aspect_ratio": "16:9",
                "duration": duration,
                "audio": False,
                "watermark": False
            }
        }
        
        response = requests.post(self.api_url, headers=headers, json=data)
        result = response.json()
        
        if response.status_code == 200 and 'output' in result:
            task_id = result['output'].get('task_id')
            return task_id
        else:
            error_msg = result.get('message', 'Unknown error')
            raise RuntimeError(f"任务创建失败: {error_msg}")
    
    def wait_for_task(self, task_id: str, timeout: int = 600) -> Dict:
        """等待任务完成并返回结果"""
        start_time = time.time()
        print(f"  ⏳ 等待任务完成: {task_id}")
        
        while time.time() - start_time < timeout:
            url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
            headers = {'Authorization': f'Bearer {self.api_key}'}
            
            response = requests.get(url, headers=headers)
            status_result = response.json()
            
            task_status = status_result.get('output', {}).get('task_status', '')
            
            if task_status == 'SUCCEEDED':
                video_url = status_result.get('output', {}).get('video_url', '')
                print(f"  ✅ 完成！")
                return {
                    'status': 'success',
                    'video_url': video_url,
                    'task_id': task_id
                }
            
            elif task_status == 'FAILED':
                error_msg = status_result.get('output', {}).get('message', 'Unknown error')
                print(f"  ❌ 失败: {error_msg}")
                return {
                    'status': 'failed',
                    'error': error_msg,
                    'task_id': task_id
                }
            
            else:
                elapsed = int(time.time() - start_time)
                print(f"  ⏳ 状态: {task_status} (已等待 {elapsed}秒)...")
                time.sleep(15)
        
        return {
            'status': 'timeout',
            'task_id': task_id
        }
    
    def run_group_a_with_consistency(self, storyboard: Dict):
        """A组：启用角色一致性"""
        print("\n" + "="*80)
        print("🎬 A组测试：启用角色一致性")
        print("="*80)
        
        character_name = storyboard.get('characters_to_test', [{}])[0].get('name', '苏清雨')
        character_ref = self.generate_character_reference(character_name)
        
        print(f"\n👤 角色参考: {character_name}")
        print(f"📝 参考描述长度: {len(character_ref)} 字符")
        
        shots = storyboard.get('shots', [])
        
        for i, shot in enumerate(shots, 1):
            print(f"\n[{i}/{len(shots)}] 分镜 {shot['shot_number']}: {shot['scene']}")
            print(f"  原始prompt长度: {len(shot['prompt'])} 字符")
            
            try:
                # 创建任务
                task_id = self.create_video_task_with_consistency(
                    prompt=shot['prompt'],
                    duration=shot['duration'],
                    character_ref=character_ref
                )
                print(f"  ✓ 任务已创建: {task_id}")
                
                # 等待完成
                result = self.wait_for_task(task_id)
                result['shot_number'] = shot['shot_number']
                result['scene'] = shot['scene']
                result['enhanced_prompt_length'] = len(shot['prompt']) + len(character_ref)
                
                self.results['group_a_with_consistency'].append(result)
                
            except Exception as e:
                print(f"  ❌ 错误: {str(e)}")
                self.results['group_a_with_consistency'].append({
                    'shot_number': shot['shot_number'],
                    'scene': shot['scene'],
                    'status': 'error',
                    'error': str(e)
                })
            
            # 避免API限流，等待一下
            if i < len(shots):
                print("  ⏸️  等待5秒再继续...")
                time.sleep(5)
    
    def run_group_b_without_consistency(self, storyboard: Dict):
        """B组：不启用角色一致性（对照组）"""
        print("\n" + "="*80)
        print("🎬 B组测试：不启用角色一致性（对照组）")
        print("="*80)
        
        shots = storyboard.get('shots', [])
        
        for i, shot in enumerate(shots, 1):
            print(f"\n[{i}/{len(shots)}] 分镜 {shot['shot_number']}: {shot['scene']}")
            print(f"  Prompt长度: {len(shot['prompt'])} 字符")
            
            try:
                # 创建任务
                task_id = self.create_video_task_without_consistency(
                    prompt=shot['prompt'],
                    duration=shot['duration']
                )
                print(f"  ✓ 任务已创建: {task_id}")
                
                # 等待完成
                result = self.wait_for_task(task_id)
                result['shot_number'] = shot['shot_number']
                result['scene'] = shot['scene']
                result['prompt_length'] = len(shot['prompt'])
                
                self.results['group_b_without_consistency'].append(result)
                
            except Exception as e:
                print(f"  ❌ 错误: {str(e)}")
                self.results['group_b_without_consistency'].append({
                    'shot_number': shot['shot_number'],
                    'scene': shot['scene'],
                    'status': 'error',
                    'error': str(e)
                })
            
            # 避免API限流
            if i < len(shots):
                print("  ⏸️  等待5秒再继续...")
                time.sleep(5)
    
    def generate_comparison_report(self, storyboard: Dict):
        """生成对比测试报告"""
        print("\n" + "="*80)
        print("📊 生成对比测试报告")
        print("="*80)
        
        group_a = self.results['group_a_with_consistency']
        group_b = self.results['group_b_without_consistency']
        
        # 统计成功率
        a_success = sum(1 for r in group_a if r.get('status') == 'success')
        b_success = sum(1 for r in group_b if r.get('status') == 'success')
        
        # 统计平均prompt长度
        a_avg_prompt = sum(r.get('enhanced_prompt_length', 0) for r in group_a) / len(group_a) if group_a else 0
        b_avg_prompt = sum(r.get('prompt_length', 0) for r in group_b) / len(group_b) if group_b else 0
        
        report = {
            'test_name': '角色一致性对比测试',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'storyboard': storyboard.get('title'),
            'test_character': storyboard.get('characters_to_test', [{}])[0].get('name'),
            'total_shots': len(storyboard.get('shots', [])),
            'group_a_with_consistency': {
                'total': len(group_a),
                'successful': a_success,
                'failed': len(group_a) - a_success,
                'avg_prompt_length': a_avg_prompt,
                'results': group_a
            },
            'group_b_without_consistency': {
                'total': len(group_b),
                'successful': b_success,
                'failed': len(group_b) - b_success,
                'avg_prompt_length': b_avg_prompt,
                'results': group_b
            },
            'comparison': {
                'prompt_length_difference': a_avg_prompt - b_avg_prompt,
                'success_rate_a': f"{(a_success/len(group_a)*100):.1f}%" if group_a else "0%",
                'success_rate_b': f"{(b_success/len(group_b)*100):.1f}%" if group_b else "0%"
            },
            'evaluation_guide': {
                'step_1': '下载A组和B组生成的所有视频',
                'step_2': '按分镜顺序对比同一角色的外观',
                'step_3': '检查以下一致性指标:',
                'metrics': [
                    '面部特征（五官、脸型）是否一致',
                    '发型发色是否保持（长黑发）',
                    '身材体型是否统一',
                    '种族特征是否稳定（东亚女性）',
                    '服装是否合理变化（应随场景变化）',
                    '表情是否自然（应符合场景）'
                ],
                'step_4': '记录哪一组的一致性更好',
                'step_5': '给出测试结论'
            }
        }
        
        # 保存报告
        report_file = f"consistency_comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 报告已保存: {report_file}")
        
        # 打印摘要
        print(f"\n📈 测试摘要:")
        print(f"  A组（有角色一致性）: {a_success}/{len(group_a)} 成功")
        print(f"  B组（无角色一致性）: {b_success}/{len(group_b)} 成功")
        print(f"  Prompt长度差异: +{a_avg_prompt - b_avg_prompt:.0f} 字符")
        
        print(f"\n🎯 下一步:")
        print(f"  1. 查看生成的视频URL")
        print(f"  2. 下载并对比视频")
        print(f"  3. 评估角色一致性效果")
        print(f"  4. 填写测试结论到报告中")
        
        return report
    
    def run_full_test(self, storyboard_file: str):
        """运行完整对比测试"""
        print("\n" + "="*80)
        print("🧪 角色一致性实际对比测试")
        print("="*80)
        print("\n⚠️  注意：此测试将实际调用API生成视频")
        print("⏱️  预计耗时：每个分镜约3-5分钟")
        print(f"📊 总计：{len(json.load(open(storyboard_file, 'r', encoding='utf-8')).get('shots', []))} × 2组 = 需要生成视频数")
        
        confirm = input("\n确认开始测试？(y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ 测试已取消")
            return
        
        try:
            # 1. 加载分镜
            storyboard = self.load_storyboard(storyboard_file)
            
            # 2. 记录测试元数据
            self.results['test_metadata'] = {
                'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'storyboard_file': storyboard_file,
                'test_purpose': '验证角色一致性机制效果'
            }
            
            # 3. 运行A组测试
            self.run_group_a_with_consistency(storyboard)
            
            # 4. 运行B组测试
            self.run_group_b_without_consistency(storyboard)
            
            # 5. 生成报告
            self.results['test_metadata']['end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            report = self.generate_comparison_report(storyboard)
            
            print("\n" + "="*80)
            print("✅ 测试完成！")
            print("="*80)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  测试被中断")
            # 保存当前进度
            self.save_progress()
        except Exception as e:
            print(f"\n❌ 测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def save_progress(self):
        """保存测试进度"""
        progress_file = f"test_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 进度已保存: {progress_file}")


def main():
    """主函数"""
    print("\n" + "="*80)
    print("🧪 角色一致性实际对比测试系统")
    print("="*80)
    print()
    
    # 测试文件
    storyboard_file = "test_consistency_storyboard.json"
    
    if not os.path.exists(storyboard_file):
        print(f"❌ 测试文件不存在: {storyboard_file}")
        return
    
    try:
        # 创建测试器
        tester = ConsistencyComparisonTest()
        
        # 运行测试
        tester.run_full_test(storyboard_file)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  测试已取消")
    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
