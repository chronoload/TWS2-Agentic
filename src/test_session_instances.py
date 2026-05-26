#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试会话实例管理器
"""

import time
import sys
sys.path.insert(0, '.')

print('=== 会话实例管理器测试 ===\n')

print('1. 加载模块...')
try:
    from mcp.extensions.session_instances import get_session_instance_manager
    print('   ✅ 加载成功')
except Exception as e:
    print('   ❌ 加载失败:', str(e))
    import traceback
    traceback.print_exc()
    exit(1)

print('\n2. 初始化管理器...')
try:
    manager = get_session_instance_manager()
    print('   ✅ 初始化成功')
except Exception as e:
    print('   ❌ 初始化失败:', str(e))
    exit(1)

print('\n3. 创建会话实例...')
try:
    conv1 = manager.create_instance('conv-1', '编程对话')
    conv2 = manager.create_instance('conv-2', '写作对话')
    print('   ✅ 创建了 2 个会话:')
    print('      -', conv1.title, '(', conv1.conversation_id[:8], ')')
    print('      -', conv2.title, '(', conv2.conversation_id[:8], ')')
except Exception as e:
    print('   ❌ 创建失败:', str(e))
    exit(1)

print('\n4. 设置活动会话...')
try:
    manager.set_active_instance('conv-1')
    active = manager.get_active_instance()
    print('   ✅ 活动会话:', active.title)
except Exception as e:
    print('   ❌ 设置失败:', str(e))

print('\n5. 创建后台任务...')
try:
    # 模拟一个长时间运行的任务
    def test_task(duration=2):
        time.sleep(duration)
        return '任务完成！'
    
    # 在 conv-1 中创建任务
    task = manager.create_background_task('conv-1', 'test_task', test_task, 1.5)
    print('   ✅ 创建任务:', task.task_id[:8])
except Exception as e:
    print('   ❌ 创建任务失败:', str(e))

print('\n6. 列出所有实例...')
try:
    instances = manager.list_instances()
    print('   ✅ 共有', len(instances), '个会话实例:')
    for inst in instances:
        active_mark = ' [活动]' if inst.is_active else ''
        tasks_running = len(inst.get_active_tasks())
        print('      -', inst.title, active_mark, '(', len(inst.background_tasks), '任务,', tasks_running, '运行中)')
except Exception as e:
    print('   ❌ 列出失败:', str(e))

print('\n7. 等待任务完成...')
time.sleep(2)

print('\n8. 检查任务状态...')
try:
    all_tasks = manager.get_all_tasks('conv-1')
    print('   ✅ conv-1 任务状态:')
    for t in all_tasks:
        result_text = t.result if t.status == 'completed' else t.error
        print('      -', t.task_type, '(', t.status, '):', result_text)
except Exception as e:
    print('   ❌ 检查失败:', str(e))

print('\n=== 所有测试完成！ ===')
