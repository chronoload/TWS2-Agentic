---
name: math-modeling-rmd
description: 数学建模论文 Rmd/Qmd 完整写作工作流
tags: [math-modeling, rmarkdown, quarto, paper, competition, workflow]
---

# 数学建模论文 Rmd/Qmd 写作工作流

## 概述

本 SKILL 提供一套完整的数学建模论文写作工作流，基于 R Markdown 和 Quarto，结合 knitr 工具链，实现从数据预处理、模型建立到论文生成的全流程自动化。

**适用场景**：
- 数学建模竞赛论文（国赛、美赛等）
- 学术论文写作
- 数据分析报告
- 可重复研究文档

**核心优势**：
- 🚀 快速启动：一键初始化项目结构
- 📝 规范写作：符合竞赛论文标准
- 🔄 可重复性：代码与文档一体化
- 📊 自动化：自动生成图表、表格、参考文献
- 🎨 美观输出：支持 PDF、HTML、Word 多种格式

---

## 快速开始

### 1. 初始化项目

```r
# 方法 1：使用初始化脚本
source(".workbuddy/skills/math-modeling-rmd/scripts/init_project.R")
init_math_modeling_project()

# 方法 2：手动创建目录结构
# 参见下方"项目结构"章节
```

### 2. 创建论文模板

```r
# 创建国赛 PDF 模板
source(".workbuddy/skills/math-modeling-rmd/scripts/create_paper.R")
create_competition_paper(
  filename = "paper/main.Rmd",
  competition = "国赛",  # 或 "美赛"
  output_format = "pdf"  # 或 "html", "both"
)
```

### 3. 编写论文

```r
# 在 RStudio 中打开 paper/main.Rmd
# 使用快捷键 Ctrl+Alt+I 插入代码块
# 使用 Ctrl+Shift+K 渲染论文
```

---

## 核心工作流

### 工作流概览

```
数据准备 → 探索性分析 → 建立模型 → 求解验证 → 论文写作 → 提交
    ↓            ↓            ↓           ↓           ↓
 R脚本        Rmd文档       R脚本      Rmd文档     最终渲染
```

### 时间分配（三天竞赛）

| 时间 | 任务 | 产出 |
|------|------|------|
| Day 1 上午 | 读题、讨论、确定思路 | 思路报告 |
| Day 1 下午 | 数据处理、问题一建模 | R 脚本、初稿 |
| Day 1 晚上 | 问题一写作、问题二建模 | 问题一初稿 |
| Day 2 上午 | 问题二求解、问题三建模 | 问题二初稿 |
| Day 2 下午 | 问题三求解、完善模型 | 问题三初稿 |
| Day 2 晚上 | 论文写作、初稿完成 | 完整初稿 |
| Day 3 上午 | 摘要撰写、模型改进 | 改进版本 |
| Day 3 下午 | 论文润色、检查排版 | 定稿 |
| Day 3 晚上 | 最终修改、提交准备 | 提交版本 |

---

## 项目结构

### 推荐目录结构

```
MathModeling_Project/
├── README.md                 # 项目说明
├── MathModeling.Rproj        # RStudio 项目文件
├── .Rprofile                 # R 启动配置
├── .gitignore                # Git 忽略文件
├── Makefile                  # 自动化构建
│
├── data/                     # 数据文件
│   ├── raw/                  # 原始数据（不纳入版本控制）
│   ├── processed/            # 清洗后数据
│   └── external/             # 外部数据
│
├── R/                        # R 脚本
│   ├── 01_data_prep.R        # 数据预处理
│   ├── 02_exploratory.R      # 探索性分析
│   ├── 03_modeling.R         # 建模脚本
│   └── utils.R               # 工具函数
│
├── models/                   # 保存的模型
├── figures/                  # 生成的图表
├── tables/                   # 生成的表格
│
├── paper/                    # 论文目录
│   ├── main.Rmd              # 主文档
│   ├── preamble.tex          # LaTeX 导言区
│   ├── csl/                  # 引用样式
│   │   └── chinese-gb7714-2015-numeric.csl
│   └── references.bib        # 参考文献
│
├── output/                   # 输出文件
│   └── .gitignore
│
└── docs/                     # 文档
    └── modeling_notes.md
```

---

## 核心资源

### 📚 参考文档（references/）

1. **algorithms.md** - 数学建模常用算法索引
   - 优化模型：线性规划、整数规划、非线性规划
   - 微分方程模型：ODE、PDE
   - 统计模型：回归、时间序列、聚类
   - 机器学习模型：决策树、神经网络
   - 图论与网络模型
   - 评价方法：AHP、TOPSIS、灰色关联
   - 模拟方法：蒙特卡洛、元胞自动机

2. **writing-standards.md** - 论文写作规范
   - 论文结构（国赛/美赛）
   - 摘要写作技巧
   - 各章节写作要点
   - 参考文献格式
   - 常见错误避免

### 🛠️ 工具脚本（scripts/）

1. **init_project.R** - 项目初始化脚本
   - 创建标准目录结构
   - 生成配置文件
   - 初始化 Git 仓库

2. **create_paper.R** - 论文模板生成
   - 国赛/美赛模板
   - PDF/HTML/Word 输出
   - 自动创建配套文件

### 📦 模板资源（assets/templates/）

1. **preamble.tex** - LaTeX 导言区模板
   - 页面设置
   - 数学环境
   - 表格图片
   - 代码高亮
   - 中文支持

---

## 使用指南

### 1. 环境配置

#### 必需软件

| 软件 | 用途 | 安装方法 |
|------|------|----------|
| R (≥4.0) | 核心计算环境 | https://cran.r-project.org/ |
| RStudio / Positron | IDE | https://posit.co/download/ |
| TinyTeX | LaTeX 环境 | `tinytex::install_tinytex()` |
| Pandoc | 文档转换 | 随 RStudio 安装 |

#### R 包安装

```r
# 核心包
install.packages(c(
  "rmarkdown", "knitr", "tinytex", "rticles", "bookdown", "quarto",
  "tidyverse", "ggplot2", "dplyr", "tidyr", "readr", "purrr",
  "kableExtra", "gt", "flextable", "stargazer",
  "here", "rprojroot", "config", "yaml", "jsonlite"
))

# 数学建模算法包
install.packages(c(
  "lpSolve", "ROI", "deSolve", "forecast", "cluster",
  "MASS", "car", "nloptr", "mice", "caret"
))
```

### 2. 论文写作流程

#### 步骤 1：准备数据

```r
# R/01_data_prep.R
library(tidyverse)

# 读取原始数据
raw_data <- read.csv("data/raw/data.csv")

# 数据清洗
clean_data <- raw_data %>%
  filter(!is.na(key_column)) %>%
  mutate(
    new_column = transform(old_column),
    category = factor(category)
  )

# 保存清洗后的数据
write.csv(clean_data, "data/processed/clean_data.csv", row.names = FALSE)
```

#### 步骤 2：建立模型

```r
# R/03_modeling.R
library(tidyverse)

# 加载数据
data <- read.csv("data/processed/clean_data.csv")

# 建立模型
model <- lm(y ~ x1 + x2, data = data)

# 保存模型
saveRDS(model, "models/model1.rds")
```

#### 步骤 3：在论文中引用

```markdown
# paper/main.Rmd

```{r load-model}
# 加载模型
model <- readRDS("../models/model1.rds")

# 模型结果
summary(model)
```

```{r model-plot, fig.cap="模型结果可视化"}
# 可视化
data <- read.csv("../data/processed/clean_data.csv")
ggplot(data, aes(x = x1, y = y)) +
  geom_point() +
  geom_smooth(method = "lm") +
  theme_minimal()
```
```

### 3. 常用代码模板

#### 三线表

```r
```{r three-line-table}
library(kableExtra)

mtcars[1:5, 1:5] %>%
  kable(
    caption = "数据预览",
    booktabs = TRUE,
    align = "c",
    digits = 2
  ) %>%
  kable_styling(
    latex_options = c("hold_position", "scale_down"),
    full_width = FALSE
  ) %>%
  row_spec(0, bold = TRUE)
```
```

#### 数学公式

```markdown
目标函数：

$$
\min_{x} f(x) = \sum_{i=1}^{n} (y_i - \hat{y}_i)^2
$$

约束条件：

$$
\begin{cases}
g_i(x) \leq 0, & i = 1, 2, \ldots, m \\
h_j(x) = 0, & j = 1, 2, \ldots, p
\end{cases}
$$
```

#### 算法伪代码

```markdown
```{=latex}
\begin{algorithm}
\caption{算法名称}
\begin{algorithmic}[1]
\Input 输入参数
\Output 输出结果
\State 初始化
\For{each $i \in [1,n]$}
    \State 执行操作
\EndFor
\State \Return 结果
\end{algorithmic}
\end{algorithm}
```
```

---

## 高级功能

### 1. 参数化报告

```yaml
---
title: "参数化报告"
params:
  dataset: "mtcars"
  alpha: 0.05
  date: !r Sys.Date()
---
```

```r
# 使用参数
data <- get(params$dataset)
alpha <- params$alpha
```

### 2. 批量渲染

```r
# 渲染多个版本
datasets <- c("mtcars", "iris", "Boston")

purrr::map(datasets, function(d) {
  rmarkdown::render(
    "paper/main.Rmd",
    params = list(dataset = d),
    output_file = paste0("output/main_", d, ".pdf")
  )
})
```

### 3. 自动化工作流

```makefile
# Makefile
all: pdf html

pdf:
	Rscript -e "rmarkdown::render('paper/main.Rmd', output_format='pdf_document')"

html:
	Rscript -e "rmarkdown::render('paper/main.Rmd', output_format='html_document')"

clean:
	rm -rf output/*
```

```bash
# 使用命令
make all     # 生成 PDF 和 HTML
make pdf     # 仅生成 PDF
make clean   # 清理输出
```

---

## 常见问题

### 1. 中文支持

**问题**：PDF 输出中文乱码

**解决方案**：
```yaml
output:
  pdf_document:
    latex_engine: xelatex
    includes:
      in_header: preamble.tex
```

在 `preamble.tex` 中添加：
```latex
\usepackage{ctex}
```

### 2. 图片大小控制

**问题**：图片太大或太小

**解决方案**：
```r
```{r plot, fig.width=8, fig.height=6, out.width="80%", dpi=300}
plot(data)
```
```

### 3. 表格跨页

**问题**：长表格无法跨页

**解决方案**：
```r
library(kableExtra)
long_table %>%
  kable(longtable = TRUE, booktabs = TRUE) %>%
  kable_styling(latex_options = c("hold_position", "repeat_header"))
```

### 4. 缓存失效

**问题**：代码修改后缓存未更新

**解决方案**：
```r
# 清除缓存
knitr::clean_cache()

# 或在 YAML 中禁用缓存
knitr::opts_chunk$set(cache = FALSE)
```

---

## 竞赛技巧

### 1. 团队协作

| 角色 | 职责 | 关键技能 |
|------|------|----------|
| 队员1（建模） | 建立模型、算法设计 | 数学推导、模型选择 |
| 队员2（编程） | 编程实现、数据处理 | R/Python 编程、可视化 |
| 队员3（写作） | 论文写作、排版美化 | 文字组织、LaTeX |

### 2. 时间管理

- ⏰ 每小时回顾进度
- 📋 使用检查清单
- 💾 频繁保存和备份
- 🔄 使用版本控制

### 3. 质量保证

- ✅ 模型验证必不可少
- ✅ 敏感性分析展示稳健性
- ✅ 结果可视化清晰明了
- ✅ 论文结构完整规范

---

## 参考资源

### 官方文档
- [R Markdown: The Definitive Guide](https://bookdown.org/yihui/rmarkdown/)
- [R Markdown Cookbook](https://bookdown.org/yihui/rmarkdown-cookbook/)
- [Quarto 官方文档](https://quarto.org/)

### 教材
- 《数学建模：算法与编程实现》（张敬信）
- 《R Markdown 指南》
- 《R 语言编程：基于 tidyverse》（张敬信）

### 本 SKILL 相关文档
- `references/algorithms.md` - 算法索引
- `references/writing-standards.md` - 写作规范
- `scripts/init_project.R` - 初始化脚本
- `scripts/create_paper.R` - 模板生成脚本
- `assets/templates/preamble.tex` - LaTeX 模板

---

## 更新日志

- **2026-03-25**: 完善项目结构，添加算法索引、写作规范、初始化脚本
- **初始版本**: 基础工作流和模板

---

**记住**：数学建模竞赛的核心是**问题分析**和**模型建立**，工具只是辅助。熟练使用本工作流可以大幅提高效率，让团队专注于核心建模工作！
