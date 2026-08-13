---
name: pdf-toc-processor
description: This skill should be used when processing PDF Table of Contents (TOC) for scanned or text-based PDFs, including detecting TOC pages, OCR recognition, and text extraction workflows with GPU acceleration support.
---

# PDF TOC Processor

This skill provides efficient workflows for processing PDF Table of Contents, supporting both scanned (image-based) and text-based PDFs with GPU-accelerated OCR.

## When to Use This Skill

Use this skill when:
- Finding TOC pages in a PDF document
- Extracting TOC text from text-based PDFs
- Performing OCR recognition on scanned PDF TOC pages
- Analyzing PDF structure and book marks
- Processing Chinese and English mixed content in PDFs

## Prerequisites and Environment

### Required Dependencies

Install Python packages:
```bash
pip install pymupdf pdfplumber easyocr
```

### GPU Acceleration

- **GPU Mode (Recommended)**: Set `gpu=True` for 3-5x speed improvement
- **CPU Fallback**: Automatically falls back to CPU if GPU unavailable
- **First Run**: Downloads OCR models (~200MB) on first execution

### Windows Path Handling

- Use raw strings for paths: `r'C:\path\to\file.pdf'`
- Supports absolute and relative paths
- Quote paths with spaces: `"C:\My Documents\file.pdf"`

## Workflow Overview

### 1. Quick Assessment Workflow

Determine PDF type and structure:

```bash
# Scan PDF and get basic info
python toc_tools/scan_pdf.py --pdf "path/to/file.pdf"

# Check page type (text vs image)
python toc_tools/read_toc2.py --pdf "path/to/file.pdf" --pages 1-20
```

**Decision Points:**
- If pages show text: Use text extraction (`read_toc.py`)
- If pages show "no text" or "image": Use OCR workflows

### 2. TOC Detection Workflow

Find TOC pages in the PDF:

```bash
# Find TOC pages (scans first 30 pages by default)
python toc_tools/find_toc_page.py --pdf "path/to/file.pdf"

# Custom scan range
python toc_tools/find_toc_page.py --pdf "path/to/file.pdf" --max-pages 50

# Force CPU mode (slower)
python toc_tools/find_toc_page.py --pdf "path/to/file.pdf" --no-gpu
```

**Output Analysis:**
- Note page numbers showing TOC keywords ("目录", "第一章", "Chapter", etc.)
- Check if multiple TOC pages exist (multi-page TOCs are common)

### 3. Text Extraction Workflow (Text-based PDFs)

Extract text directly from TOC pages:

```bash
# Extract text from specific pages
python toc_tools/read_toc.py --pdf "path/to/file.pdf" --pages 10-12

# Extract from single page
python toc_tools/read_toc.py --pdf "path/to/file.pdf" --pages 10
```

### 4. OCR Recognition Workflow (Scanned PDFs)

Perform OCR on TOC pages:

```bash
# OCR specific pages with GPU acceleration
python toc_tools/ocr_toc.py --pdf "path/to/file.pdf" --pages 10-12

# Save OCR results to JSON
python toc_tools/ocr_toc.py --pdf "path/to/file.pdf" --pages 10-12 --output toc_results.json

# CPU mode (no GPU available)
python toc_tools/ocr_toc.py --pdf "path/to/file.pdf" --pages 10-12 --no-gpu
```

## Configuration

### Default PDF Path

Edit `toc_tools/config.py` to set default PDF:

```python
DEFAULT_PDF = r'C:\path\to\your\file.pdf'
```

### OCR Settings

Adjust OCR defaults in `toc_tools/config.py`:

```python
OCR_USE_GPU = True      # GPU acceleration
OCR_MAX_PAGES = 30      # Scan page limit
```

## Common Use Cases

### Use Case 1: Process a New PDF

1. Quick scan:
   ```bash
   python toc_tools/scan_pdf.py --pdf "new_file.pdf"
   ```

2. Determine type:
   - Text shown → Text extraction
   - "No text" shown → OCR workflow

3. Execute appropriate workflow based on type

### Use Case 2: Find Multi-page TOC

```bash
# Scan more pages to find complete TOC
python toc_tools/find_toc_page.py --pdf "file.pdf" --max-pages 100

# OCR multiple pages
python toc_tools/ocr_toc.py --pdf "file.pdf" --pages 10-25 --output full_toc.json
```

### Use Case 3: Batch Processing Multiple PDFs

```bash
# Process multiple PDFs with default config
for file in *.pdf; do
  python toc_tools/find_toc_page.py --pdf "$file"
  python toc_tools/ocr_toc.py --pdf "$file" --pages 10-12 --output "${file%.pdf}_toc.json"
done
```

## Troubleshooting

### Issue: Import Errors

**Problem**: `ModuleNotFoundError: No module named 'config'`

**Solution**: Run scripts from `toc_tools/` directory:
```bash
cd toc_tools
python scan_pdf.py --pdf "path/to/file.pdf"
```

### Issue: OCR is Slow

**Problem**: OCR taking too long on large PDFs

**Solution**: 
1. Ensure GPU is enabled: `--gpu` (default)
2. Reduce scan pages: `--max-pages 30`
3. Use targeted page ranges: `--pages 10-15`

### Issue: First Run Downloads Models

**Problem**: First OCR run takes extra time

**Explanation**: EasyOCR downloads models (~200MB) on first use

**Solution**: Keep network connection active during first run

### Issue: Chinese Characters Garbled

**Problem**: Chinese text appears as garbled characters

**Solution**: Ensure UTF-8 encoding is used for output files:
```bash
python toc_tools/ocr_toc.py --pdf "file.pdf" --pages 10-12 --output toc.json
# toc.json uses UTF-8 encoding by default
```

### Issue: File Not Found

**Problem**: `错误: 文件不存在 - path/to/file.pdf`

**Solution**: Check path format:
- Use absolute paths: `"C:\Users\Name\Desktop\file.pdf"`
- Quote paths with spaces: `"C:\My Documents\file.pdf"`
- Use raw strings in Python: `r'path\to\file.pdf'`

## Performance Tips

1. **Use GPU Acceleration**: Default mode, 3-5x faster than CPU
2. **Limit Scan Pages**: Use `--max-pages` to avoid scanning entire PDF
3. **Target Specific Pages**: Use `--pages 10-12` instead of scanning all pages
4. **Save Results**: Use `--output` to save OCR results for later analysis
5. **Reuse Models**: First run downloads models, subsequent runs are faster

## Reference Resources

See `toc_tools/README.md` for:
- Detailed parameter documentation
- Complete usage examples
- Performance optimization guidelines
- Advanced workflow examples
