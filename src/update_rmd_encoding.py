
"""
给所有现有 Rmd 文件添加 Windows 中文路径支持
"""
from pathlib import Path

setup_code = '''```{r setup, include=FALSE}
# Windows中文路径支持
if (.Platform$OS.type == "windows") {
  # 设置正确的编码选项
  options(encoding = "UTF-8")
  Sys.setlocale("LC_ALL", "Chinese (Simplified)_China.UTF-8")
  # 或者尝试更通用的：
  # Sys.setlocale("LC_ALL", "")
}
knitr::opts_chunk$set('''

notes_dir = Path(__file__).parent / "Notes"

print("正在扫描 Rmd 文件...")
rmd_files = list(notes_dir.rglob("*.Rmd"))
print(f"找到 {len(rmd_files)} 个 Rmd 文件\n")

updated_count = 0
for rmd_file in rmd_files:
    try:
        content = rmd_file.read_text(encoding="utf-8")
        
        # 检查是否已经添加过我们的代码
        if "# Windows中文路径支持" in content:
            print(f"⏭ 跳过: {rmd_file.name} (已更新)")
            continue
        
        # 查找 setup 代码块位置并插入我们的代码
        if "```{r setup, include=FALSE}" in content and "knitr::opts_chunk$set(" in content:
            # 找到位置并替换
            old_code = "```{r setup, include=FALSE}\nknitr::opts_chunk$set("
            new_content = content.replace(old_code, setup_code)
            
            if new_content != content:
                rmd_file.write_text(new_content, encoding="utf-8")
                print(f"✅ 已更新: {rmd_file.name}")
                updated_count += 1
            else:
                print(f"⚠ 未找到插入位置: {rmd_file.name}")
        else:
            print(f"⚠ 未找到标准 setup 块: {rmd_file.name}")
            
    except Exception as e:
        print(f"❌ 处理失败 {rmd_file.name}: {e}")

print(f"\n✅ 完成！共更新了 {updated_count} 个文件！")
