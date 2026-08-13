# -*- coding: utf-8 -*-
"""下载 vditor/katex/pdfjs 到本地 static，实现真正的本地优先加载"""
import os
import sys
import urllib.request

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'mcp', 'server', 'static')

FILES = [
    # 本地路径 ← CDN URL
    ('vditor/dist/index.min.js', 'https://unpkg.com/vditor@3.10.7/dist/index.min.js'),
    ('vditor/dist/index.css', 'https://unpkg.com/vditor@3.10.7/dist/index.css'),
    ('vditor/dist/css/content-theme/light.css', 'https://unpkg.com/vditor@3.10.7/dist/css/content-theme/light.css'),
    ('vditor/dist/css/content-theme/dark.css', 'https://unpkg.com/vditor@3.10.7/dist/css/content-theme/dark.css'),
    ('vditor/dist/js/lute/lute.min.js', 'https://unpkg.com/vditor@3.10.7/dist/js/lute/lute.min.js'),
    ('vditor/js/katex/katex.min.js', 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js'),
    ('vditor/js/katex/katex.min.css', 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css'),
    ('vditor/js/katex/mhchem.min.js', 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/mhchem.min.js'),
    ('vditor/js/katex/auto-render.min.js', 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js'),
    ('pdfjs/pdf.min.js', 'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.min.js'),
    ('pdfjs/pdf.worker.min.js', 'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js'),
    # vditor 图标字体/图片（index.css 内部相对引用）
    ('vditor/dist/images/emoji.png', 'https://unpkg.com/vditor@3.10.7/dist/images/emoji.png'),
]

ok, fail = 0, 0
for rel, url in FILES:
    dest = os.path.join(BASE, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        with open(dest, 'wb') as f:
            f.write(data)
        print('OK  %-52s %.2fMB' % (rel, len(data) / 1e6))
        ok += 1
    except Exception as e:
        print('FAIL %-52s %s' % (rel, e))
        fail += 1

print('DONE ok=%d fail=%d' % (ok, fail))
