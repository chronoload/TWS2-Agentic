---
name: rmarkdown
description: R Markdown - dynamic documents, presentations, dashboards, and reports in R
---

# R Markdown Skill

Use this skill when working with R Markdown, creating reproducible research documents, or building interactive reports in R.

## R Markdown Overview

R Markdown is an authoring framework for reproducible research that combines R code with Markdown text. It supports multiple output formats including HTML, PDF, Word documents, presentations, and interactive dashboards.

### Core Concepts

- **Literate Programming**: Mix code (R) with narrative text
- **Reproducibility**: Documents are fully reproducible from source
- **Multiple Outputs**: Single source → HTML, PDF, Word, slides, etc.
- **Interactive**: Embed Shiny apps, HTML widgets, interactive plots
- **Extensible**: Custom formats and templates

## Basic R Markdown Document

### Document Structure

```markdown
---
title: "My Document"
author: "Your Name"
date: "`r Sys.Date()`"
output: html_document
---

# Introduction

This is a paragraph with **bold** and *italic* text.

## Code Blocks

```{r}
summary(mtcars)
plot(mtcars$mpg, mtcars$hp)
```

## Inline Code

The dataset has `r nrow(mtcars)` rows and `r ncol(mtcars)` columns.

## Output Formats

### HTML Document

```yaml
output:
  html_document:
    theme: cosmo
    highlight: pygments
    toc: true
    toc_float: true
    code_folding: show
```

### PDF Document

```yaml
output:
  pdf_document:
    latex_engine: xelatex
    toc: true
    number_sections: true
```

### Word Document

```yaml
output: word_document:
  reference_docx: template.docx
```

## Code Chunk Options

### Basic Options

| Option | Description | Default |
|--------|-------------|---------|
| `echo` | Display code | TRUE |
| `eval` | Evaluate code | TRUE |
| `include` | Include code and output | TRUE |
| `message` | Display messages | TRUE |
| `warning` | Display warnings | TRUE |
| `error` | Stop on errors | FALSE |
| `results` | How to display results | markup |
| `fig.cap` | Figure caption | NULL |
| `fig.width` | Figure width (inches) | 7 |
| `fig.height` | Figure height (inches) | 7 |

### Usage Examples

```markdown
```{r chunk-name, echo=FALSE, fig.cap="My Plot"}
plot(cars)
```

```{r chunk-name-2, results="hide", warning=FALSE}
# Suppress messages
data(iris)
summary(iris)
```

```{r chunk-name-3, eval=FALSE}
# Code only, don't evaluate
x <- 1 + 1
```

```

### Global Options

```r
knitr::opts_chunk$set(
  echo = TRUE,
  message = FALSE,
  warning = FALSE,
  fig.width = 8,
  fig.height = 6
)
```

## Output Formats

### Documents

**HTML Document** (`html_document`)
- Default output format
- Supports themes and syntax highlighting
- Self-contained or with external assets
- Math rendering via MathJax

**PDF Document** (`pdf_document`)
- Uses LaTeX
- Requires TeX distribution (TeX Live, MiKTeX)
- Supports citations and bibliography
- Page numbering and section headings

**Word Document** (`word_document`)
- Microsoft Word format
- Customizable with templates
- Tables and figures preserved
- Reference document for styling

**Markdown Document** (`markdown_document`)
- Pure Markdown output
- Compatible with other Markdown processors
- Useful for GitHub or static site generators

**Rich Text Format** (`rtf_document`)
- Rich Text Format
- Compatible with older systems

**OpenDocument Text** (`opendocument_text_document`)
- OpenDocument format (LibreOffice)

### Presentations

**ioslides Presentation** (`ioslides_presentation`)
- HTML5 slideshow
- Google style templates
- Transitions and animations
- Auto-scaling slides

**Slidy Presentation** (`slidy_presentation`)
- W3C HTML slideshow
- Slide navigation
- Speaker notes support

**Beamer Presentation** (`beamer_presentation`)
- LaTeX Beamer slides
- Academic standard
- Professional templates
- Mathematical formulas

**reveal.js Presentation** (`revealjs_presentation`)
- Modern HTML5 slideshow
- 3D transitions
- Plugin support
- Responsive design

**PowerPoint Presentation** (`powerpoint_presentation`)
- Microsoft PowerPoint output
- Template-based
- Slide layouts preserved

**Shower Presentation** (`shower_presentation`)
- Lightweight HTML slideshow
- Modern design
- Keyboard navigation

### Books and Websites

**Bookdown** (`bookdown`)
- Multi-chapter books
- Cross-references
- GitBook-style output
- PDF/HTML/EPUB formats

**pkgdown** (`pkgdown`)
- R package documentation
- Automatic documentation website
- Reference manual
- Articles and vignettes

**R Markdown Website** (`rmarkdown_site`)
- Multi-page websites
- Navigation menu
- RSS feeds
- Blog support (blogdown)

### Dashboards

**flexdashboard** (`flexdashboard`)
- Interactive dashboards
- Flexible grid layout
- Components (value boxes, charts)
- Supports Shiny interactivity

**Shiny Documents** (`flexdashboard` with Shiny)
- Interactive web applications
- Reactive components
- Input widgets
- Dynamic updates

## Interactive Features

### HTML Widgets

**Overview**
HTML widgets bring JavaScript interactivity to R Markdown documents.

**Popular Widgets**
- `plotly` - Interactive plots
- `DT` - Interactive tables
- `leaflet` - Interactive maps
- `dygraphs` - Time series
- `networkD3` - Network graphs
- `threejs` - 3D plots

**Example**

```r
library(plotly)
plot_ly(mtcars, x = ~mpg, y = ~hp, 
        color = ~factor(cyl), type = "scatter")
```

### Shiny Documents

**Embedded Shiny**
- Add interactivity without separate app file
- Input widgets and reactive outputs
- Server-side execution
- Requires Shiny server

**Structure**

```markdown
---
title: "Interactive Document"
runtime: shiny
---

## Inputs

```{r}
sliderInput("n", "Number of points:", 
            min = 10, max = 100, value = 50)
```

## Output

```{r}
renderPlot({
  plot(rnorm(input$n))
})
```
```

### Shiny Widgets

**Interactive Components**
- `actionButton()` - Action buttons
- `sliderInput()` - Numeric sliders
- `textInput()` - Text input
- `selectInput()` - Dropdown menus
- `checkboxInput()` - Checkboxes
- `radioButtons()` - Radio buttons
- `dateRangeInput()` - Date ranges

## Parameterized Reports

### Declaring Parameters

```yaml
---
title: "Monthly Report"
params:
  start_date: "2024-01-01"
  end_date: "2024-01-31"
  region: "North"
output: html_document
---
```

### Using Parameters

```r
# Access parameters
params$start_date
params$region

# Use in code
library(dplyr)
data %>%
  filter(date >= params$start_date,
         date <= params$end_date) %>%
  filter(region == params$region)
```

### Rendering with Parameters

```r
rmarkdown::render("report.Rmd", 
  params = list(
    start_date = "2024-02-01",
    end_date = "2024-02-28",
    region = "South"
  )
)
```

## Citations and Bibliography

### Markdown Citations

```markdown
The work of @knuth1984 established modern literate programming.
Multiple citations @knuth1984; @xie2015.

See also the discussion in [@knuth1984, pp. 99-101].
```

### References

```
---
bibliography: references.bib
csl: apa.csl
---
```

### BibTeX Entry

```
@book{knuth1984,
  title={The TeXbook},
  author={Knuth, Donald E},
  year={1984},
  publisher={Addison-Wesley}
}
```

## Learnr (Interactive Tutorials)

### Creating Tutorials

```yaml
---
title: "My Tutorial"
output: learnr::tutorial
---
```

### Exercise Types

**Regular Exercise**

```r
exercise_1 <- question("What is 2 + 2?",
  answer("2"),
  answer("4", correct = TRUE),
  answer("5")
)
```

**Code Exercise**

````markdown
```{r addition-exercise, exercise=TRUE}
# Add 3 and 5
___ + ___
```
````

**Quiz**

```r
quiz(
  question("What is the capital of France?",
    answer("London"),
    answer("Paris", correct = TRUE),
    answer("Berlin")
  ),
  question("What is 2 * 3?",
    answer("5"),
    answer("6", correct = TRUE),
    answer("7")
  )
)
```

### Tutorial Features

- **Exercises**: Code chunks with predefined solutions
- **Quizzes**: Multiple-choice questions
- **Videos**: Embedded video content
- **Navigation**: Progress tracking
- **Shiny**: Interactive components

## Custom Formats

### Creating Custom Formats

```r
# In _output.yml
custom_format:
  from: html_document
  css: styles.css
  includes:
    before_body: header.html
    after_body: footer.html
```

### Deriving from Existing Formats

```yaml
---
output:
  custom_document:
    theme: flatly
    highlight: tango
    toc: true
---
```

## Appearance and Styling

### HTML Themes

```yaml
output:
  html_document:
    theme: default  # default, cerulean, journal, flatly, 
                    # readable, spacelab, united, cosmo, 
                    # lumen, paper, sandstone, simplex, yeti
```

### Syntax Highlighting

```yaml
output:
  html_document:
    highlight: default  # default, tango, pygments, kate, 
                        # monochrome, espresso, zenburn, haddock, textmate
```

### Custom CSS

```markdown
---
output:
  html_document:
    css: custom.css
---
```

```css
/* custom.css */
body {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
}

code {
  background-color: #f5f5f5;
}
```

## Books with bookdown

### Book Structure

```
mybook/
├── index.Rmd          # Preface
├── 01-intro.Rmd       # Chapter 1
├── 02-methods.Rmd     # Chapter 2
├── 03-results.Rmd     # Chapter 3
├── _bookdown.yml      # Book configuration
├── _output.yml        # Output settings
└── README.md
```

### _bookdown.yml

```yaml
book_filename: "my-book"
chapter_name: "Chapter "
output_dir: "docs"
new_session: yes
```

### Cross-references

```markdown
See @fig-example for details.

```{r example, fig.cap="Example Figure"}
plot(cars)
```
```

## rticles (Journal Articles)

### Journal Templates

```r
install.packages("rticles")
```

```yaml
---
output:
  rticles::plos_article:
  abstract: |
    The abstract text...
  bibliography: myrefs.bib
---
```

**Supported Journals**
- PLoS
- Elsevier
- Springer
- Taylor & Francis
- ACM
- IEEE
- Many more

## Publishing

### Publishing to RStudio Connect

```r
rsconnect::deployDoc("document.Rmd")
```

### Publishing to GitHub Pages

```bash
# Using blogdown
blogdown::build_site()
```

### Publishing to RPubs

```r
rpubs::upload("document.Rmd")
```

## Best Practices

### Document Organization

1. **Clear Structure**: Use consistent heading levels
2. **Chunk Naming**: Name all code chunks for clarity
3. **Global Options**: Set chunk options globally
4. **Code Folding**: Use `code_folding` for long documents
5. **Table of Contents**: Always include TOC for long documents

### Code Style

1. **Load Packages in Setup**: Put `library()` calls in first chunk
2. **Set Seed**: Use `set.seed()` for reproducibility
3. **Clean Up**: Remove temporary objects
4. **Comment**: Add comments to explain complex code
5. **Test**: Test code chunks individually

### Output Management

1. **Figure Size**: Set appropriate figure dimensions
2. **Caching**: Use `cache=TRUE` for time-consuming code
3. **Message Control**: Suppress messages with `message=FALSE`
4. **Error Handling**: Decide on error handling strategy
5. **Output Formats**: Test multiple output formats

## Common Issues and Solutions

### LaTeX Errors

**Problem**: PDF compilation fails
**Solution**: Install complete TeX distribution, use `xelatex` engine

```yaml
output:
  pdf_document:
    latex_engine: xelatex
```

### Figures Not Displaying

**Problem**: Figures missing in Word output
**Solution**: Use `fig.cap` for all figures

```r
```{r, fig.cap="My Figure"}
plot(cars)
```
```

### Chinese Characters

**Problem**: Chinese characters don't display in PDF
**Solution**: Use `xelatex` and Chinese fonts

```yaml
output:
  pdf_document:
    latex_engine: xelatex
    includes:
      in_header: chinese.tex
```

## Useful Functions

```r
# Render document
rmarkdown::render("document.Rmd")

# Render with parameters
rmarkdown::render("report.Rmd", params = list(date = "2024-01-01"))

# Preview document
rmarkdown::draft("new.Rmd", template = "html_document")

# Get available formats
names(rmarkdown::supported_formats())
```

## Learning Resources

### Official Documentation

- [R Markdown: The Definitive Guide](https://bookdown.org/yihui/rmarkdown/)
- [R Markdown Cookbook](https://bookdown.org/yihui/rmarkdown-cookbook/)
- [bookdown: Authoring Books](https://bookdown.org/yihui/bookdown/)
- [flexdashboard](https://rmarkdown.rstudio.com/flexdashboard/)

### Online Tutorials

- RStudio Primers: https://rstudio.cloud/learn/primers
- Learnr Tutorial: https://rstudio-education.github.io/learnr/
- Coursera courses on R Markdown

### Books

- "R Markdown: The Definitive Guide" by Yihui Xie
- "R Markdown Cookbook" by Yihui Xie, Christophe Dervieux, Emily Riederer
- "bookdown: Authoring Books with R Markdown" by Yihui Xie

## When to Use This Skill

Always use this skill when:
- Creating reproducible research documents
- Writing reports in R
- Building presentations or slides
- Creating interactive dashboards
- Authoring books or tutorials
- Developing R packages with vignettes
- Publishing technical documentation
