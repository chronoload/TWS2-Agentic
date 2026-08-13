---
name: rmarkdown-cookbook
description: Practical recipes and solutions for common R Markdown problems - use when looking for specific solutions, workarounds, or community-sourced examples
---

# R Markdown Cookbook Skill

Use this skill when looking for **practical solutions**, **recipes**, and **workarounds** for specific R Markdown problems and tasks. This cookbook provides short, focused examples drawn from Stack Overflow and community resources.

## When to Use This Skill

Load this skill when:
- Looking for specific R Markdown solutions
- Need practical examples for common problems
- Want to customize output formats (HTML, PDF, Word)
- Need workarounds for limitations
- Looking for community-sourced solutions
- Need to implement specific formatting requirements
- Want to optimize R Markdown workflow
- Working with multiple output formats
- Need to handle tables, citations, or cross-references
- Integrating Python, Shell, or other languages
- Creating animations, diagrams, or interactive content

## Skill Overview

R Markdown Cookbook complements the comprehensive reference in `rmarkdown` skill by providing:
- **Practical recipes** for common problems
- **Short, focused examples** instead of lengthy explanations
- **Community-sourced solutions** from Stack Overflow and blog posts
- **Quick reference** for everyday tasks
- **Advanced tricks** for experienced users

**Authors**: Yihui Xie, Christophe Dervieux, Emily Riederer
**License**: Creative Commons Attribution-NonCommercial-ShareAlike 4.0

## Skill Structure

```
.codebuddy/skills/rmarkdown-cookbook/
├── skill.md                          # This file - main documentation
├── scripts/                          # Executable scripts
│   └── convert_html_to_md.py         # HTML to Markdown converter
├── references/                       # Reference documentation (detailed recipes)
│   ├── README.md                     # This file - reference guide
│   ├── INDEX.md                      # File index with search tips
│   ├── installation.md               # Pandoc, LaTeX, R packages setup
│   ├── basics.md                     # Code chunks, notebooks, scripts
│   ├── document_elements.md          # Page breaks, citations, TOC, dates
│   ├── formatting.md                 # Font color, indentation, alignment
│   ├── latex_output.md               # PDF-specific recipes
│   ├── html_output.md                # HTML-specific recipes (CSS, tabs, etc)
│   ├── word_output.md                # Word-specific recipes (templates, styles)
│   ├── multiple_outputs.md           # Conditional output, widgets
│   ├── tables.md                     # knitr::kable, kableExtra, long tables
│   ├── chunk_options.md              # Chunk options, caching, evaluation
│   ├── output_hooks.md               # Source redaction, line numbers
│   ├── chunk_hooks.md                # Plot cropping, timing, optimization
│   ├── other_languages.md            # Python, Shell, JavaScript, SAS
│   ├── project_management.md         # External scripts, child docs, working dir
│   ├── workflow.md                   # Shortcuts, rendering, parameters, trackdown
│   ├── best_practices.md             # Project structure, Git, organization
│   └── common_problems.md            # Troubleshooting guide (FAQ)
└── assets/                           # Assets used in output
    └── templates/                    # Document templates
        ├── html_template.css         # Custom CSS template
        ├── pdf_template.tex           # LaTeX preamble template
        └── word_template.docx        # Word reference template
```

## Quick Start

### Installation

```r
# Core packages
install.packages(c("rmarkdown", "knitr", "kableExtra"))

# Authoring tools
install.packages(c("bookdown", "blogdown", "learnr"))

# LaTeX for PDF output
install.packages("tinytex")
tinytex::install_tinytex()

# Visualization
install.packages(c("DiagrammeR", "plotly", "patchwork"))
```

### Basic Usage

```r
# Render document
rmarkdown::render("document.Rmd")

# Render with parameters
rmarkdown::render("report.Rmd", 
                  params = list(region = "North", 
                               date = "2024-01-01"))

# Interactive dashboard
flexdashboard::run("dashboard.Rmd")
```

## Using Reference Documentation

### How to Search

1. **Identify your problem category**:
   - Installation/setup → `installation.md`
   - Code chunks/notebooks → `basics.md`
   - Page elements → `document_elements.md`
   - Formatting → `formatting.md`
   - PDF issues → `latex_output.md`
   - HTML styling → `html_output.md`
   - Word documents → `word_output.md`
   - Multiple formats → `multiple_outputs.md`
   - Tables → `tables.md`
   - Chunk behavior → `chunk_options.md`
   - Output customization → `output_hooks.md` or `chunk_hooks.md`
   - Other languages → `other_languages.md`
   - Project structure → `project_management.md`
   - Workflow tips → `workflow.md`

2. **Use INDEX.md** for quick topic overview

3. **Search within files**: Use Ctrl+F to find specific keywords

### Example Workflows

#### Problem: "How do I add page breaks in PDF?"

1. Identify category: PDF output → `latex_output.md`
2. Search for "page break"
3. Solution found: `\newpage` or `\newpage\noindent`

#### Problem: "How do I create a styled table?"

1. Identify category: Tables → `tables.md`
2. Read kableExtra section
3. Copy example and customize

#### Problem: "How do I embed Python code?"

1. Identify category: Other languages → `other_languages.md`
2. Find Python section
3. Use ````{python}``` code chunk

## Using Scripts

### convert_html_to_md.py

Convert R Markdown Cookbook HTML pages to Markdown:

```bash
cd C:\Users\qu\WorkBuddy\Claw
python .codebuddy/skills/rmarkdown-cookbook/scripts/convert_html_to_md.py
```

**Features**:
- Fetches HTML from bookdown.org
- Converts to clean Markdown
- Preserves code blocks and tables
- Saves to `crawl_output/clean_md/`
- Supports incremental updates

## Using Assets

### Templates

Copy and customize templates from `assets/templates/`:

```r
# Use custom CSS
output:
  html_document:
    css: .codebuddy/skills/rmarkdown-cookbook/assets/templates/html_template.css

# Use custom LaTeX preamble
output:
  pdf_document:
    includes:
      in_header: .codebuddy/skills/rmarkdown-cookbook/assets/templates/pdf_template.tex
```

## Journal and Presentation Templates

### rticles 包 - 期刊论文模板（44 个）

rticles 提供学术期刊投稿的 R Markdown 模板，支持主流期刊格式：

**计算机科学**：ACM、IEEE、LNCS、LIPIcs、JOSS  
**自然科学**：ACS、AGU、AMS、IOP、MNRAS、Copernicus  
**生命科学**：Bioinformatics、Biometrics、PeerJ、PLOS、Wellcome  
**统计学**：ASA、IMS、JSS、RSS、Statistics in Medicine  
**多学科**：Elsevier、Springer、PNAS、Frontiers、MDPI、Sage  
**中文支持**：CTeX 模板

**使用方法**：
```r
# RStudio: 文件 → 新建文件 → R Markdown → From Template
# 命令行：
rmarkdown::draft("paper.Rmd", template = "elsevier", package = "rticles")
```

详见：`references/rticles-templates.md`

### binb 包 - Beamer 演示文稿主题（3 个）

binb 提供精美的 Beamer 幻灯片主题：

1. **Metropolis**（推荐）：现代简约风格，适合技术演讲
2. **IQSS**：专业学术风格，适合学术会议
3. **Monash**：机构定制风格，可自定义颜色

**使用方法**：
```yaml
---
output:
  binb::metropolis: default
---
```

详见：`references/binb-templates.md`

## Common Problems Quick Reference

| Problem | Reference File | Solution Summary |
|---------|---------------|------------------|
| Chinese characters in PDF | `latex_output.md` | Use `xelatex` engine |
| Large tables in PDF | `tables.md` | Use `booktabs`, `longtable` |
| Plots too small | `formatting.md` | Adjust `fig.width`, `dpi` |
| Code not executing | `chunk_options.md` | Check `eval` option |
| Too much output | `chunk_options.md` | Use `results='hide'` |
| Page breaks not working | `latex_output.md` | Use `\newpage` |
| Custom styling in HTML | `html_output.md` | Add custom CSS |
| Word template issues | `word_output.md` | Edit `reference.docx` |
| Citations not showing | `document_elements.md` | Check `.bib` file |
| Cross-references broken | `document_elements.md` | Check label syntax |
| Journal submission format | `rticles-templates.md` | Use rticles package |
| Beamer presentation theme | `binb-templates.md` | Use binb package |

## Best Practices

### 1. Project Organization

```
project/
├── data/
├── scripts/
├── figures/
├── report.Rmd
├── references.bib
└── custom.css
```

### 2. Global Chunk Options

```r
knitr::opts_chunk$set(
  echo = TRUE,
  warning = FALSE,
  message = FALSE,
  fig.width = 8,
  fig.height = 6,
  dpi = 300
)
```

### 3. Named Chunks

```r
```{r setup}
library(tidyverse)
```

```{r load-data}
data <- read_csv("data.csv")
```
```

### 4. Version Control

```bash
git init
git add .
git commit -m "Initial report"
```

### 5. Parameterized Reports

```yaml
---
params:
  region: "North"
  date: "2024-01-01"
---
```

```r
params$region  # Access parameter
```

## Related Skills

| Skill | Purpose | When to Use |
|-------|---------|-------------|
| `rmarkdown` | Comprehensive reference | Learning concepts, understanding architecture |
| `rmarkdown-cookbook` | Practical recipes | Solving specific problems, finding quick fixes |
| `bookdown` | Authoring books | Creating multi-chapter documents |
| `blogdown` | Building websites | Creating blogs and documentation sites |
| `flexdashboard` | Creating dashboards | Building interactive dashboards |
| `learnr` | Interactive tutorials | Creating educational content |

## Resources

### Official Documentation

- [R Markdown Cookbook](https://bookdown.org/yihui/rmarkdown-cookbook/) - Primary source
- [R Markdown: The Definitive Guide](https://bookdown.org/yihui/rmarkdown/) - Comprehensive reference
- [knitr Documentation](https://yihui.org/knitr/) - Chunk options and hooks

### Community

- Stack Overflow: [r-markdown tag](https://stackoverflow.com/questions/tagged/r-markdown)
- RStudio Community: https://community.rstudio.com/
- R Markdown Slack: https://rmarkdown.slack.com/

### Key Packages

- [kableExtra](https://haozhu233.github.io/kableExtra/) - Beautiful tables
- [bookdown](https://bookdown.org/) - Authoring books
- [blogdown](https://bookdown.org/yihui/blogdown/) - Websites
- [flexdashboard](https://rmarkdown.rstudio.com/flexdashboard/) - Dashboards
- [learnr](https://rstudio-education.github.io/learnr/) - Tutorials

## Skill Maintenance

### Version

- **Current Version**: 1.0.0
- **Last Updated**: 2025-03-25
- **Based on**: R Markdown Cookbook (bookdown.org/yihui/rmarkdown-cookbook/)

### Feedback

If you find issues or have suggestions:
1. Check `common_problems.md` for troubleshooting
2. Refer to official documentation
3. Search Stack Overflow for community solutions
4. Consider updating skill with new recipes

---

**Remember**: This skill complements the `rmarkdown` skill. Use `rmarkdown` for learning concepts and architecture, use this skill for practical problem-solving with recipes and examples.
