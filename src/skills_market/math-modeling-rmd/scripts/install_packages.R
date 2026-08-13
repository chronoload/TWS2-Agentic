#!/usr/bin/env Rscript

# ==================================================
# 数学建模 R 包安装脚本
# 用途：一键安装所有必需的 R 包
# 使用：Rscript install_packages.R
# ==================================================

# 定义包列表
packages <- list(
  # 核心包
  core = c(
    "rmarkdown",    # R Markdown 核心
    "knitr",        # 代码执行引擎
    "tinytex",      # LaTeX 管理
    "bookdown",     # 书籍/长文档
    "quarto"        # Quarto 支持
  ),
  
  # 数据处理
  data = c(
    "tidyverse",    # 数据科学工具集
    "readr",        # 数据读取
    "readxl",       # Excel 读取
    "haven",        # SPSS/Stata 读取
    "data.table",   # 高性能数据处理
    "janitor"       # 数据清洗
  ),
  
  # 可视化
  visualization = c(
    "ggplot2",      # 核心绑图包
    "patchwork",    # 图形组合
    "cowplot",      # 出版级图形
    "ggpubr",       # 出版级图形
    "RColorBrewer", # 配色方案
    "viridis",      # 色盲友好配色
    "scales"        # 坐标轴缩放
  ),
  
  # 表格
  tables = c(
    "kableExtra",   # 美化表格
    "gt",           # 现代表格
    "flextable",    # Word 表格
    "stargazer",    # 回归结果表格
    "xtable"        # LaTeX 表格
  ),
  
  # 数学建模算法
  modeling = c(
    "lpSolve",      # 线性规划
    "ROI",          # 优化接口
    "nloptr",       # 非线性优化
    "deSolve",      # 微分方程
    "forecast",     # 时间序列
    "tseries",      # 时间序列分析
    "cluster",      # 聚类分析
    "MASS",         # 统计方法
    "car",          # 回归诊断
    "mgcv"          # 广义可加模型
  ),
  
  # 机器学习
  ml = c(
    "caret",        # 机器学习框架
    "randomForest", # 随机森林
    "rpart",        # 决策树
    "e1071",        # SVM
    "nnet",         # 神经网络
    "xgboost"       # 梯度提升
  ),
  
  # 评价方法
  evaluation = c(
    "FuzzyAHP",     # AHP 方法
    "mcda",         # 多准则决策
    "Rmpfr"         # 高精度计算
  ),
  
  # 工具包
  utilities = c(
    "here",         # 路径管理
    "rprojroot",    # 项目根目录
    "config",       # 配置文件
    "yaml",         # YAML 处理
    "jsonlite",     # JSON 处理
    "glue",         # 字符串拼接
    "stringr",      # 字符串处理
    "lubridate",    # 日期时间
    "purrr"         # 函数式编程
  ),
  
  # 网络和图论
  network = c(
    "igraph",       # 图论计算
    "ggraph",       # 网络可视化
    "tidygraph"     # 图数据处理
  ),
  
  # 特殊功能
  special = c(
    "DiagrammeR",   # 流程图
    "latex2exp",    # LaTeX 公式
    "animation",    # 动画
    "plotly",       # 交互图形
    "DT"            # 交互表格
  )
)

# 安装函数
install_packages <- function(package_list, category_name) {
  cat("\n====================================\n")
  cat(sprintf("  安装 %s 包\n", category_name))
  cat("====================================\n")
  
  for (pkg in package_list) {
    if (requireNamespace(pkg, quietly = TRUE)) {
      cat(sprintf("✓ %s 已安装\n", pkg))
    } else {
      cat(sprintf("• 安装 %s...\n", pkg))
      tryCatch({
        install.packages(pkg, dependencies = TRUE)
        cat(sprintf("✓ %s 安装成功\n", pkg))
      }, error = function(e) {
        cat(sprintf("✗ %s 安装失败: %s\n", pkg, e$message))
      })
    }
  }
}

# 安装 TinyTeX
install_latex <- function() {
  cat("\n====================================\n")
  cat("  安装 LaTeX 环境\n")
  cat("====================================\n")
  
  if (tinytex::is_tinytex()) {
    cat("✓ TinyTeX 已安装\n")
  } else {
    cat("• 安装 TinyTeX...\n")
    tinytex::install_tinytex()
    cat("✓ TinyTeX 安装成功\n")
  }
}

# 验证安装
verify_installation <- function() {
  cat("\n====================================\n")
  cat("  验证安装\n")
  cat("====================================\n")
  
  # 检查核心功能
  checks <- list(
    pandoc = rmarkdown::pandoc_available(),
    latex = tinytex::is_tinytex(),
    rmarkdown = requireNamespace("rmarkdown", quietly = TRUE),
    knitr = requireNamespace("knitr", quietly = TRUE),
    ggplot2 = requireNamespace("ggplot2", quietly = TRUE),
    dplyr = requireNamespace("dplyr", quietly = TRUE)
  )
  
  for (name in names(checks)) {
    status <- ifelse(checks[[name]], "✓", "✗")
    cat(sprintf("%s %s\n", status, name))
  }
}

# 主函数
main <- function() {
  cat("\n====================================\n")
  cat("  数学建模 R 包安装脚本\n")
  cat("====================================\n")
  
  # 设置 CRAN 镜像
  options(repos = c(CRAN = "https://mirrors.tuna.tsinghua.edu.cn/CRAN/"))
  cat("\n✓ 使用清华大学 CRAN 镜像\n")
  
  # 安装各类包
  for (category in names(packages)) {
    install_packages(packages[[category]], category)
  }
  
  # 安装 LaTeX
  install_latex()
  
  # 验证安装
  verify_installation()
  
  # 完成提示
  cat("\n====================================\n")
  cat("  ✓ 安装完成！\n")
  cat("====================================\n\n")
  
  cat("提示：\n")
  cat("1. 如有安装失败的包，请手动安装\n")
  cat("2. 运行 tinytex::tlmgr_update() 更新 LaTeX\n")
  cat("3. 重启 R 会话以加载新包\n")
}

# 执行
main()
