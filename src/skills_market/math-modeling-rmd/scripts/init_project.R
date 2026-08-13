#!/usr/bin/env Rscript

# ==================================================
# 数学建模项目初始化脚本
# 用途：创建标准化的项目目录结构
# 使用：Rscript init_project.R [项目名称]
# ==================================================

# 获取项目名称（可选）
project_name <- ifelse(
  length(commandArgs(trailingOnly = TRUE)) > 0,
  commandArgs(trailingOnly = TRUE)[1],
  "MathModeling_Project"
)

# 定义目录结构
dirs <- c(
  "data/raw",
  "data/processed",
  "data/external",
  "R",
  "models",
  "figures",
  "tables",
  "paper/csl",
  "output",
  "docs"
)

# 创建目录
create_directories <- function(base_path, dirs) {
  for (dir in dirs) {
    full_path <- file.path(base_path, dir)
    if (!dir.exists(full_path)) {
      dir.create(full_path, recursive = TRUE, showWarnings = FALSE)
      message("✓ 创建目录: ", full_path)
    } else {
      message("• 目录已存在: ", full_path)
    }
  }
}

# 创建 .gitignore
create_gitignore <- function(base_path) {
  gitignore_content <- c(
    "# 数据文件",
    "data/raw/*",
    "!data/raw/.gitkeep",
    "data/processed/*",
    "!data/processed/.gitkeep",
    "",
    "# 模型和输出",
    "models/*",
    "!models/.gitkeep",
    "figures/*",
    "!figures/.gitkeep",
    "tables/*",
    "!tables/.gitkeep",
    "output/*",
    "!output/.gitkeep",
    "",
    "# R 相关",
    ".Rproj.user",
    ".Rhistory",
    ".RData",
    ".Ruserdata",
    ".Renviron",
    "",
    "# LaTeX 相关",
    "*.aux",
    "*.log",
    "*.out",
    "*.toc",
    "*.bbl",
    "*.blg",
    "*.fls",
    "*.fdb_latexmk",
    "*.synctex.gz",
    "*.nav",
    "*.snm",
    "",
    "# 其他",
    "renv/library/",
    "*.html",
    "*.nb.html",
    "*_files/",
    ".DS_Store",
    "Thumbs.db"
  )
  
  gitignore_path <- file.path(base_path, ".gitignore")
  if (!file.exists(gitignore_path)) {
    writeLines(gitignore_content, gitignore_path)
    message("✓ 创建文件: .gitignore")
  } else {
    message("• 文件已存在: .gitignore")
  }
}

# 创建 .gitkeep 文件
create_gitkeep <- function(base_path, dirs) {
  for (dir in dirs) {
    gitkeep_path <- file.path(base_path, dir, ".gitkeep")
    if (!file.exists(gitkeep_path)) {
      file.create(gitkeep_path)
    }
  }
  message("✓ 创建 .gitkeep 文件")
}

# 创建 README.md
create_readme <- function(base_path, project_name) {
  readme_content <- sprintf(
'---
title: "%s"
author: "Your Name"
date: "`r Sys.Date()`"
---

# %s

## 项目说明

这是一个数学建模竞赛论文项目。

## 目录结构

```
%s/
├── data/              # 数据文件
│   ├── raw/           # 原始数据
│   ├── processed/     # 处理后数据
│   └── external/      # 外部数据
├── R/                 # R 脚本
├── models/            # 保存的模型
├── figures/           # 生成的图表
├── tables/            # 生成的表格
├── paper/             # 论文目录
├── output/            # 输出文件
└── docs/              # 文档
```

## 环境配置

```r
# 安装必需包
install.packages(c(
  "rmarkdown", "knitr", "tinytex", "tidyverse", 
  "kableExtra", "ggplot2", "bookdown"
))

# 安装 LaTeX
tinytex::install_tinytex()
```

## 使用方法

1. 将原始数据放入 `data/raw/`
2. 编辑 `R/` 中的脚本进行数据处理和建模
3. 编辑 `paper/main.Rmd` 撰写论文
4. 渲染论文：`rmarkdown::render("paper/main.Rmd")`

## 注意事项

- 数据文件不要提交到 Git（已在 .gitignore 中排除）
- 定期备份项目
- 保持代码可重复性

## 作者

- 姓名：Your Name
- 日期：%s

## 许可证

MIT License
',
    project_name, project_name, project_name, Sys.Date()
  )
  
  readme_path <- file.path(base_path, "README.md")
  if (!file.exists(readme_path)) {
    writeLines(readme_content, readme_path)
    message("✓ 创建文件: README.md")
  } else {
    message("• 文件已存在: README.md")
  }
}

# 创建 RStudio 项目文件
create_rproj <- function(base_path, project_name) {
  rproj_content <- sprintf(
'Version: 1.0

RestoreWorkspace: No
SaveWorkspace: No
AlwaysSaveHistory: Default

EnableCodeIndexing: Yes
UseSpacesForTab: Yes
NumSpacesForTab: 2
Encoding: UTF-8

RnwWeave: Sweave
LaTeX: pdfLaTeX

AutoAppendNewline: Yes
StripTrailingWhitespace: Yes

BuildType: Makefile
'
  )
  
  rproj_path <- file.path(base_path, paste0(project_name, ".Rproj"))
  if (!file.exists(rproj_path)) {
    writeLines(rproj_content, rproj_path)
    message("✓ 创建文件: ", project_name, ".Rproj")
  } else {
    message("• 文件已存在: ", project_name, ".Rproj")
  }
}

# 创建 .Rprofile
create_rprofile <- function(base_path) {
  rprofile_content <-
'# .Rprofile - R 启动配置

# 设置 CRAN 镜像
options(repos = c(CRAN = "https://mirrors.tuna.tsinghua.edu.cn/CRAN/"))

# 设置字符串为 UTF-8
options(encoding = "UTF-8")

# 设置 ggplot2 主题
if (requireNamespace("ggplot2", quietly = TRUE)) {
  ggplot2::theme_set(ggplot2::theme_minimal(base_size = 12))
}

# 输出欢迎消息
message("✓ R 环境已加载")
message("当前工作目录: ", getwd())
'

  rprofile_path <- file.path(base_path, ".Rprofile")
  if (!file.exists(rprofile_path)) {
    writeLines(rprofile_content, rprofile_path)
    message("✓ 创建文件: .Rprofile")
  } else {
    message("• 文件已存在: .Rprofile")
  }
}

# 主函数
main <- function() {
  cat("\n====================================\n")
  cat("  数学建模项目初始化脚本\n")
  cat("====================================\n\n")
  
  # 获取当前工作目录
  base_path <- getwd()
  message("项目名称: ", project_name)
  message("项目路径: ", base_path, "\n")
  
  # 执行初始化步骤
  message("【步骤 1/6】创建目录结构...")
  create_directories(base_path, dirs)
  
  message("\n【步骤 2/6】创建 .gitignore...")
  create_gitignore(base_path)
  
  message("\n【步骤 3/6】创建 .gitkeep 文件...")
  create_gitkeep(base_path, dirs)
  
  message("\n【步骤 4/6】创建 README.md...")
  create_readme(base_path, project_name)
  
  message("\n【步骤 5/6】创建 RStudio 项目文件...")
  create_rproj(base_path, project_name)
  
  message("\n【步骤 6/6】创建 .Rprofile...")
  create_rprofile(base_path)
  
  # 完成提示
  cat("\n====================================\n")
  cat("  ✓ 项目初始化完成！\n")
  cat("====================================\n\n")
  
  message("下一步操作：")
  message("1. 在 RStudio 中打开 ", project_name, ".Rproj")
  message("2. 将原始数据放入 data/raw/")
  message("3. 复制论文模板：")
  message("   file.copy('.workbuddy/skills/math-modeling-rmd/assets/templates/cumcm.Rmd', 'paper/main.Rmd')")
  message("4. 开始写作！")
}

# 执行
main()
