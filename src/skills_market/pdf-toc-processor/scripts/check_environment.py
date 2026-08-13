"""
Environment Check Script for PDF TOC Processor
Checks all dependencies and GPU availability
"""
import sys
import os

def check_dependencies():
    """Check if all required packages are installed"""
    required_packages = {
        'pymupdf': 'fitz',
        'pdfplumber': 'pdfplumber',
        'easyocr': 'easyocr',
        'numpy': 'numpy',
    }

    missing = []
    for package_name, import_name in required_packages.items():
        try:
            __import__(import_name)
            print(f"[OK] {package_name}")
        except ImportError:
            missing.append(package_name)
            print(f"[MISSING] {package_name}")

    return missing

def check_gpu():
    """Check if GPU is available for EasyOCR"""
    try:
        import easyocr
        # EasyOCR automatically detects GPU
        print("[INFO] GPU detection:")
        print("  EasyOCR will use GPU if CUDA is available")
        print("  Run with --gpu flag (default) to enable")
        print("  Run with --no-gpu flag to force CPU mode")
    except ImportError:
        print("[SKIP] GPU check (easyocr not installed)")

def check_config():
    """Check if config.py exists"""
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'toc_tools', 'config.py')
    if os.path.exists(config_path):
        print(f"[OK] config.py found: {config_path}")
        try:
            sys.path.insert(0, os.path.dirname(config_path))
            from config import DEFAULT_PDF, OCR_USE_GPU, OCR_MAX_PAGES
            print(f"  DEFAULT_PDF: {DEFAULT_PDF[:50]}...")
            print(f"  OCR_USE_GPU: {OCR_USE_GPU}")
            print(f"  OCR_MAX_PAGES: {OCR_MAX_PAGES}")
        except Exception as e:
            print(f"[WARN] Could not read config.py: {e}")
    else:
        print(f"[WARN] config.py not found: {config_path}")

def main():
    print("="*60)
    print("PDF TOC Processor - Environment Check")
    print("="*60)
    print()

    print("1. Checking Python Dependencies:")
    print("-" * 40)
    missing = check_dependencies()
    print()

    print("2. Checking GPU Availability:")
    print("-" * 40)
    check_gpu()
    print()

    print("3. Checking Configuration:")
    print("-" * 40)
    check_config()
    print()

    if missing:
        print("="*60)
        print("MISSING PACKAGES:")
        print(f"  {', '.join(missing)}")
        print("\nInstall with:")
        print(f"  pip install {' '.join(missing)}")
        print("="*60)
        sys.exit(1)
    else:
        print("="*60)
        print("[SUCCESS] All dependencies are installed!")
        print("You can now use PDF TOC Processor")
        print("="*60)

if __name__ == "__main__":
    main()
