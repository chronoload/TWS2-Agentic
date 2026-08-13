# -*- coding: utf-8 -*-
"""检查备份 zip 是否含 .git（寻找主仓库历史/remote）"""
import zipfile
import os

ZIPS = ['TS2.0.zip', 'TS2.7.zip', 'TS2-mica.zip', 'TS2--zip.zip',
        'T_S2.zip', 'TS2。8_1_1.zip', 'TS22.10.zip']

base = os.path.dirname(os.path.abspath(__file__))
for z in ZIPS:
    p = os.path.join(base, z)
    if not os.path.exists(p):
        print(z, 'NOT FOUND')
        continue
    try:
        with zipfile.ZipFile(p) as f:
            names = f.namelist()
            has_git = any('/.git/' in n or n.startswith('.git/') for n in names)
            has_config = any(n.endswith('.git/config') for n in names)
            print(z, 'size=%.1fMB' % (os.path.getsize(p) / 1e6),
                  'has_git=', has_git, 'has_config=', has_config)
            if has_config:
                for n in names:
                    if n.endswith('.git/config'):
                        print('  CONFIG:', n)
    except Exception as e:
        print(z, 'ERR', e)
