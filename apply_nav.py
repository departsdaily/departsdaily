#!/usr/bin/env python3
"""Inject the canonical nav + header fix into every page.
Idempotent: safe to re-run. Run from the repo root:  python apply_nav.py site
"""
import sys, os, re, glob

root = sys.argv[1] if len(sys.argv) > 1 else "site"
pages = [p for p in glob.glob(os.path.join(root, "**", "*.html"), recursive=True)
         if "/daily/" not in p.replace("\\", "/")]
changed = []

for p in pages:
    s = open(p, encoding="utf-8").read()
    orig = s
    deep = os.sep + "destinations" + os.sep in p
    pre = "../" if deep else ""

    # 1. stylesheet after board.css
    if "nav-fix.css" not in s:
        s = re.sub(r'(<link rel="stylesheet" href="' + re.escape(pre) + r'css/board\.css">)',
                   r'\1\n<link rel="stylesheet" href="' + pre + 'css/nav-fix.css">', s, count=1)

    # 2. nav.js before </head> (defer so it never blocks paint)
    if "js/nav.js" not in s:
        s = s.replace("</head>", f'<script src="{pre}js/nav.js" defer></script>\n</head>', 1)

    # 3. make sure a .hnav exists for nav.js to fill
    if 'class="hnav"' not in s and 'class="wrap hbar"' in s:
        s = s.replace('<div class="wrap hbar">',
                      '<div class="wrap hbar">\n  <nav class="hnav" aria-label="Site"></nav>', 1)

    if s != orig:
        open(p, "w", encoding="utf-8").write(s)
        changed.append(p)

print(f"{len(changed)}/{len(pages)} pages updated")
for c in changed[:6]: print("  ", c)
if len(changed) > 6: print(f"   … and {len(changed)-6} more")
