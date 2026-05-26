
"""
清理 Rmd 缓存脚本
"""
import shutil
from pathlib import Path

base_dir = Path(__file__).parent / "Notes"

print("正在查找并清理缓存文件夹...")

cache_folders = []
for course_dir in base_dir.iterdir():
    if course_dir.is_dir():
        # 查找该课程目录下的所有缓存文件夹
        for item in course_dir.iterdir():
            if item.is_dir() and item.name.endswith("_cache"):
                cache_folders.append(item)

if not cache_folders:
    print("\n🎉 没有找到缓存文件夹，您的项目很干净！")
else:
    print(f"\n找到 {len(cache_folders)} 个缓存文件夹：")
    for folder in cache_folders:
        print(f"  - {folder.name}")
    
    confirm = input("\n是否删除这些缓存文件夹？(y/n): ").lower().strip()
    
    if confirm == 'y':
        for folder in cache_folders:
            try:
                shutil.rmtree(folder)
                print(f"✓ 已删除: {folder.name}")
            except Exception as e:
                print(f"✗ 删除失败 {folder.name}: {e}")
        
        print("\n✅ 缓存清理完成！重新渲染 Rmd 时会自动重建缓存。")
    else:
        print("操作已取消。")

# 额外清理：.Rhistory
rhistory = base_dir / "综合代数学与现代几何课程" / ".Rhistory"
if rhistory.exists():
    print(f"\n找到历史文件: {rhistory.name}")
    del_rhistory = input("是否删除 .Rhistory？(y/n): ").lower().strip()
    if del_rhistory == 'y':
        try:
            rhistory.unlink()
            print("✓ .Rhistory 已删除")
        except Exception as e:
            print(f"✗ 删除失败: {e}")

print("\n清理工作结束！")
