#!/usr/bin/env python3
"""Write new harm summaries into pipeline/harm_summaries.xlsx. Never overwrites a summary that is
already there (yours or the Google Sheet's always win).

  python3 pipeline/scripts/harm_apply.py new.json

new.json: [{"ccn": "415067", "inspection_date": "2026-07-20", "tag": "F0658", "what_happened": "..."}]
"""
import json, os, sys
from openpyxl import load_workbook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "harm_summaries.xlsx")
BY = "Claude (draft for kg's review)"
new = json.load(open(sys.argv[1], encoding="utf-8"))
wb = load_workbook(PATH); ws = wb["Harm citations"]
hdr = [c.value for c in ws[1]]; col = {h: i + 1 for i, h in enumerate(hdr)}
rows = {}
for r in range(2, ws.max_row + 1):
    k = (str(ws.cell(r, col["ccn"]).value).replace(".0", "").zfill(6), str(ws.cell(r, col["inspection_date"]).value)[:10], ws.cell(r, col["tag"]).value)
    rows[k] = r
problems, done = [], 0
for n in new:
    k = (str(n["ccn"]).zfill(6), n["inspection_date"][:10], n["tag"])
    w = (n.get("what_happened") or "").strip()
    if k not in rows: problems.append(f"{k}: not in the harm summaries list"); continue
    if not w: problems.append(f"{k}: empty summary"); continue
    if "—" in w: problems.append(f"{k}: contains an em dash"); continue
    if len(w) > 700: problems.append(f"{k}: longer than 700 characters ({len(w)})"); continue
    r = rows[k]
    if str(ws.cell(r, col["what_happened"]).value or "").strip():
        print(f"skipped {k}: already has a summary"); continue
    ws.cell(r, col["what_happened"]).value = w
    ws.cell(r, col["summarized_by"]).value = BY
    done += 1
if problems:
    print("\n".join("ERROR: " + p for p in problems)); sys.exit(1)
wb.save(PATH)
print(f"wrote {done} summary(ies) to harm_summaries.xlsx")

# Also add them straight into the published data.js, without rebuilding it. The live data.js can hold
# changes made outside the build scripts, and a rebuild would erase them.
DATA = os.path.join(os.path.dirname(ROOT), "data.js")
t = open(DATA, encoding="utf-8").read()
marker = '"harm_summaries":{'
i = t.find(marker)
if i < 0:
    print("ERROR: harm_summaries not found in data.js"); sys.exit(1)
start = i + len(marker)
d = json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))
have = d.get("harm_summaries", {})
add = []
for n in new:
    k = f"{str(n['ccn']).zfill(6)}|{n['inspection_date'][:10]}|{n['tag']}"
    if k not in have and (n.get("what_happened") or "").strip():
        add.append(json.dumps(k, ensure_ascii=False) + ":" + json.dumps(n["what_happened"].strip(), ensure_ascii=False))
if add:
    t = t[:start] + ",".join(add) + ("," if t[start] != "}" else "") + t[start:]
    json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))   # still valid
    open(DATA, "w", encoding="utf-8").write(t)
print(f"added {len(add)} summary(ies) to data.js")
