# 创建数学建模竞赛论文模板
# 使用方法：source("scripts/create_paper.R")

create_competition_paper <- function(
    filename = "paper/main.Rmd",
    competition = c("国赛", "美赛"),
    output_format = c("pdf", "html", "both")
) {
  #' 创建数学建模竞赛论文模板
  #' @param filename 输出文件名
  #' @param competition 竞赛类型（国赛或美赛）
  #' @param output_format 输出格式
  
  competition <- match.arg(competition)
  output_format <- match.arg(output_format)
  
  # 根据竞赛类型选择模板
  if (competition == "国赛") {
    template <- create_chinese_template(output_format)
  } else {
    template <- create_english_template(output_format)
  }
  
  # 写入文件
  writeLines(template, filename)
  message("✓ 论文模板已创建: ", filename)
  
  # 创建配套文件
  create_supporting_files(dirname(filename))
  
  invisible(TRUE)
}

# 国赛模板
create_chinese_template <- function(output_format) {
  yaml_header <- switch(output_format,
    "pdf" = c(
      "---",
      "title: \"基于XXX模型的XXX问题研究\"",
      "subtitle: \"202X年数学建模竞赛论文\"",
      "author:",
      "  - \"队员1^[学校1，邮箱1]\"",
      "  - \"队员2^[学校2，邮箱2]\"",
      "  - \"队员3^[学校3，邮箱3]\"",
      "date: \"`r Sys.Date()`\"",
      "output:",
      "  pdf_document:",
      "    latex_engine: xelatex",
      "    includes:",
      "      in_header: preamble.tex",
      "    fig_caption: true",
      "    number_sections: true",
      "    toc: false",
      "    extra_dependencies:",
      "      ctex: []",
      "      geometry: [top=2.5cm, bottom=2.5cm, left=2.5cm, right=2.5cm]",
      "      fancyhdr: []",
      "      lastpage: []",
      "      booktabs: []",
      "      multirow: []",
      "      graphicx: []",
      "      amsmath: []",
      "      amssymb: []",
      "      amsthm: []",
      "      bm: []",
      "bibliography: references.bib",
      "csl: csl/chinese-gb7714-2015-numeric.csl",
      "---"
    ),
    "html" = c(
      "---",
      "title: \"基于XXX模型的XXX问题研究\"",
      "subtitle: \"202X年数学建模竞赛论文\"",
      "author:",
      "  - \"队员1\"",
      "  - \"队员2\"",
      "  - \"队员3\"",
      "date: \"`r Sys.Date()`\"",
      "output:",
      "  html_document:",
      "    toc: true",
      "    toc_float: true",
      "    code_folding: show",
      "    theme: flatly",
      "    highlight: tango",
      "bibliography: references.bib",
      "---"
    ),
    "both" = c(
      "---",
      "title: \"基于XXX模型的XXX问题研究\"",
      "subtitle: \"202X年数学建模竞赛论文\"",
      "author:",
      "  - \"队员1^[学校1，邮箱1]\"",
      "  - \"队员2^[学校2，邮箱2]\"",
      "  - \"队员3^[学校3，邮箱3]\"",
      "date: \"`r Sys.Date()`\"",
      "output:",
      "  pdf_document:",
      "    latex_engine: xelatex",
      "    includes:",
      "      in_header: preamble.tex",
      "    fig_caption: true",
      "    number_sections: true",
      "    toc: false",
      "  html_document:",
      "    toc: true",
      "    toc_float: true",
      "    code_folding: show",
      "    theme: flatly",
      "bibliography: references.bib",
      "---"
    )
  )
  
  body <- c(
    "",
    "```{r setup, include=FALSE}",
    "knitr::opts_chunk$set(",
    "  echo = FALSE,",
    "  message = FALSE,",
    "  warning = FALSE,",
    "  fig.width = 8,",
    "  fig.height = 6,",
    "  dpi = 300,",
    "  fig.align = 'center',",
    "  out.width = '80%'",
    ")",
    "",
    "# 加载包",
    "library(tidyverse)",
    "library(kableExtra)",
    "library(ggplot2)",
    "```",
    "",
    "## 摘要",
    "",
    "本文针对XXX问题，建立了XXX模型，主要工作如下：",
    "",
    "针对问题一，基于XXX理论，建立了XXX模型。通过对数据的XXX分析，",
    "确定了XXX参数，求解得到XXX。模型检验结果显示XXX。",
    "",
    "针对问题二，采用XXX方法，构建了XXX模型。考虑XXX因素的影响，",
    "运用XXX算法求解，得到XXX结果。敏感性分析表明XXX。",
    "",
    "针对问题三，在问题二的基础上，引入XXX变量，建立了XXX模型。",
    "通过XXX优化方法，得到XXX最优解。验证结果XXX。",
    "",
    "本文模型具有XXX优点，创新点在于XXX。模型可用于XXX场景，",
    "具有较好的XXX应用价值。",
    "",
    "**关键词：** 关键词1；关键词2；关键词3；关键词4；关键词5",
    "",
    "## 一、问题重述",
    "",
    "### 1.1 问题背景",
    "",
    "XXX是一个重要的问题。近年来，随着XXX的发展，XXX问题日益突出。",
    "该问题涉及XXX领域，对XXX具有重要意义。",
    "",
    "### 1.2 问题提出",
    "",
    "题目要求解决以下问题：",
    "",
    "1. **问题一**：XXX。要求XXX。",
    "",
    "2. **问题二**：XXX。要求XXX。",
    "",
    "3. **问题三**：XXX。要求XXX。",
    "",
    "## 二、问题分析",
    "",
    "### 2.1 问题一分析",
    "",
    "问题一要求XXX。这是一个XXX问题，核心在于XXX。",
    "",
    "首先，需要对数据进行XXX分析，提取XXX特征。",
    "",
    "其次，考虑XXX因素的影响，建立XXX关系。",
    "",
    "最后，通过XXX方法求解，得到XXX结果。",
    "",
    "### 2.2 问题二分析",
    "",
    "问题二在问题一的基础上，要求XXX。",
    "",
    "### 2.3 问题三分析",
    "",
    "问题三要求XXX。",
    "",
    "## 三、模型假设",
    "",
    "为了简化问题并建立合理的数学模型，本文做出以下假设：",
    "",
    "1. **假设1**：XXX。理由：XXX。",
    "",
    "2. **假设2**：XXX。理由：XXX。",
    "",
    "3. **假设3**：XXX。理由：XXX。",
    "",
    "## 四、符号说明",
    "",
    "| 符号 | 含义 | 单位 |",
    "|:----:|:-----|:----:|",
    "| $x$ | 自变量 | - |",
    "| $y$ | 因变量 | - |",
    "| $\\alpha$ | 参数 | - |",
    "",
    "## 五、模型的建立与求解",
    "",
    "### 5.1 问题一的模型",
    "",
    "#### 5.1.1 模型建立",
    "",
    "目标函数：",
    "",
    "$$",
    "\\min_{x} f(x) = \\sum_{i=1}^{n} (y_i - \\hat{y}_i)^2",
    "$$",
    "",
    "约束条件：",
    "",
    "$$",
    "\\begin{cases}",
    "g_i(x) \\leq 0, & i = 1, 2, \\ldots, m \\\\",
    "h_j(x) = 0, & j = 1, 2, \\ldots, p",
    "\\end{cases}",
    "$$",
    "",
    "#### 5.1.2 模型求解",
    "",
    "```{r model1-code, echo=TRUE, eval=FALSE}",
    "# 数据加载",
    "data <- read.csv(\"../data/processed/clean_data.csv\")",
    "",
    "# 模型求解",
    "result <- optimize_model(data)",
    "```",
    "",
    "```{r model1-result}",
    "# 结果展示（示例数据）",
    "result_df <- data.frame(",
    "  变量 = c(\"x1\", \"x2\", \"x3\"),",
    "  数值 = c(1.23, 4.56, 7.89),",
    "  误差 = c(0.01, 0.02, 0.03)",
    ")",
    "",
    "kable(result_df,",
    "  caption = \"模型求解结果\",",
    "  booktabs = TRUE,",
    "  digits = 2",
    ") %>%",
    "  kable_styling(latex_options = \"hold_position\")",
    "```",
    "",
    "#### 5.1.3 结果分析",
    "",
    "```{r model1-plot, fig.cap=\"模型结果可视化\"}",
    "# 可视化（示例数据）",
    "set.seed(123)",
    "plot_data <- data.frame(",
    "  x = 1:10,",
    "  y = cumsum(rnorm(10))",
    ")",
    "",
    "ggplot(plot_data, aes(x, y)) +",
    "  geom_point() +",
    "  geom_line() +",
    "  labs(",
    "    title = \"模型结果趋势图\",",
    "    x = \"时间\",",
    "    y = \"数值\"",
    "  ) +",
    "  theme_minimal()",
    "```",
    "",
    "从图表可以看出XXX。",
    "",
    "### 5.2 问题二的模型",
    "",
    "### 5.3 问题三的模型",
    "",
    "## 六、模型评价",
    "",
    "### 6.1 模型优点",
    "",
    "本文建立的模型具有以下优点：",
    "",
    "1. **XXX方面**：模型XXX，能够XXX。",
    "",
    "2. **XXX方面**：采用XXX方法，提高了XXX。",
    "",
    "### 6.2 模型缺点",
    "",
    "模型存在以下不足：",
    "",
    "1. **XXX局限**：模型假设了XXX，可能XXX。",
    "",
    "### 6.3 模型改进",
    "",
    "针对上述不足，可从以下方面改进：",
    "",
    "1. **XXX改进**：引入XXX，考虑XXX因素。",
    "",
    "## 参考文献",
    "",
    "## 附录",
    "",
    "### 附录A：核心代码",
    "",
    "```{r appendix-code, echo=TRUE, eval=FALSE}",
    "# 完整代码见 R/ 目录",
    "```"
  )
  
  c(yaml_header, body)
}

# 创建配套文件
create_supporting_files <- function(paper_dir = "paper") {
  # 创建 preamble.tex
  preamble_content <- c(
    "% 数学建模论文 LaTeX 导言区",
    "",
    "% 页面设置",
    "\\usepackage{geometry}",
    "\\geometry{a4paper, top=2.5cm, bottom=2.5cm, left=2.5cm, right=2.5cm}",
    "",
    "% 页眉页脚",
    "\\usepackage{fancyhdr}",
    "\\pagestyle{fancy}",
    "\\fancyhf{}",
    "\\fancyhead[C]{\\small 数学建模竞赛论文}",
    "\\fancyfoot[C]{\\thepage}",
    "\\renewcommand{\\headrulewidth}{0.4pt}",
    "",
    "% 数学环境",
    "\\usepackage{amsmath, amssymb, amsthm}",
    "\\usepackage{bm}",
    "",
    "% 定理环境",
    "\\newtheorem{theorem}{定理}",
    "\\newtheorem{lemma}{引理}",
    "\\newtheorem{definition}{定义}",
    "\\newtheorem{assumption}{假设}",
    "",
    "% 表格",
    "\\usepackage{booktabs}",
    "\\usepackage{multirow}",
    "\\usepackage{array}",
    "",
    "% 图片",
    "\\usepackage{graphicx}",
    "\\graphicspath{{../figures/}}",
    "",
    "% 中文支持",
    "\\usepackage{ctex}"
  )
  
  preamble_file <- file.path(paper_dir, "preamble.tex")
  if (!file.exists(preamble_file)) {
    writeLines(preamble_content, preamble_file)
    message("✓ 创建 preamble.tex")
  }
  
  # 创建 references.bib
  bib_content <- c(
    "@book{zhang2026,",
    "  author = {张敬信},",
    "  title = {数学建模：算法与编程实现},",
    "  publisher = {人民邮电出版社},",
    "  year = {2026}",
    "}",
    "",
    "@book{xie2026,",
    "  author = {Yihui Xie},",
    "  title = {R Markdown: The Definitive Guide},",
    "  publisher = {CRC Press},",
    "  year = {2018}",
    "}"
  )
  
  bib_file <- file.path(paper_dir, "references.bib")
  if (!file.exists(bib_file)) {
    writeLines(bib_content, bib_file)
    message("✓ 创建 references.bib")
  }
  
  # 创建 csl 目录（如果需要）
  csl_dir <- file.path(paper_dir, "csl")
  if (!dir.exists(csl_dir)) {
    dir.create(csl_dir, recursive = TRUE)
    message("✓ 创建 csl 目录")
  }
  
  invisible(TRUE)
}

# 交互式使用
if (interactive()) {
  # 默认创建国赛 PDF 模板
  create_competition_paper(
    filename = "paper/main.Rmd",
    competition = "国赛",
    output_format = "pdf"
  )
}
