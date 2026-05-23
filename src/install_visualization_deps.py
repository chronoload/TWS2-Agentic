#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 可视化依赖安装脚本
"""

import subprocess
import sys
import os

def install_package(package):
    """安装单个包"""
    try:
        print(f"🔧 正在安装: {package}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 安装失败: {package}")
        return False

def check_package(package):
    """检查包是否已安装"""
    try:
        __import__(package)
        return True
    except ImportError:
        return False

def main():
    print("=" * 60)
    print("🔬 WS2 科研分析、可视化与爬虫依赖安装工具")
    print("=" * 60)
    
    packages = [
        # 可视化库
        ("matplotlib", "matplotlib"),
        ("plotly", "plotly"),
        ("networkx", "networkx"),
        ("numpy", "numpy"),
        # 论文解析库
        ("PyPDF2", "PyPDF2"),
        ("docx", "python-docx"),
        ("bs4", "beautifulsoup4"),
        # 爬虫库
        ("aiohttp", "aiohttp"),
        ("lxml", "lxml"),
        ("requests", "requests"),
        ("dateutil", "python-dateutil"),
        ("urllib3", "urllib3"),
        ("chardet", "chardet"),
    ]
    
    print("\n📋 检查依赖状态:")
    all_installed = True
    for import_name, pip_name in packages:
        installed = check_package(import_name)
        status = "✅ 已安装" if installed else "❌ 未安装"
        if import_name in ["matplotlib", "plotly", "networkx", "numpy"]:
            desc = "可视化"
        elif import_name in ["aiohttp", "lxml", "requests", "dateutil", "urllib3", "chardet"]:
            desc = "网络爬虫"
        else:
            desc = "论文解析"
        print(f"   {import_name:<15} {desc:<10} {status}")
        if not installed:
            all_installed = False
    
    if all_installed:
        print("\n🎉 所有依赖已就绪！")
        print("\n可以直接启动WS2程序了。")
        return
    
    print("\n" + "=" * 60)
    response = input("\n❓ 是否现在安装缺失的依赖？(y/n): ").strip().lower()
    
    if response != 'y':
        print("\n👋 取消安装。")
        return
    
    print("\n" + "=" * 60)
    print("🚀 开始安装依赖...")
    print("=" * 60)
    
    success_count = 0
    for import_name, pip_name in packages:
        if not check_package(import_name):
            if install_package(pip_name):
                success_count += 1
        else:
            print(f"⏭️  {import_name} 已安装，跳过")
            success_count += 1
    
    print("\n" + "=" * 60)
    print(f"📊 安装完成: {success_count}/{len(packages)}")
    
    if success_count == len(packages):
        print("\n🎉 所有依赖安装成功！")
        print("\n现在可以启动WS2程序使用可视化功能了。")
    else:
        print("\n⚠️ 部分包安装失败，建议手动安装。")
        print("   运行: pip install matplotlib plotly networkx numpy")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
