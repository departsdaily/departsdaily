#!/usr/bin/env python3
"""Inject today's deals.json into the site/index.html DEALS block."""
import json, re

B = json.load(open("deals.json"))
rows = []
for d in B["deals"]:
    d2 = d["d2"] or d["d1"]
    rows.append({
        "to": d["to"], "city": d["city"], "price": d["price"],
        "varpct": "{}% BELOW TYPICAL".format(d["disc"]),
        "d1": d["d1"], "d2": d2,
        "dates": d["d1"][5:].replace("-", "/") + "-" + d2[5:].replace("-", "/"),
        "al": d["airline"], "stops": d["stops"]})
block = "const DEALS={CLT:" + json.dumps(rows) + "};"
html = open("site/index.html").read()
html = re.sub(r"const DEALS=\{CLT:\[.*?\]\};", block, html, flags=re.S)
open("site/index.html", "w").write(html)
print("site updated with", len(rows), "deals")
