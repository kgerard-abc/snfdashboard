#!/usr/bin/env python3
"""List harm citations (severity G-L) in pipeline/harm_summaries.xlsx that have no summary yet,
grouped by inspection report, newest first. Prints JSON.

  python3 pipeline/scripts/harm_todo.py [--limit N]   (N = max reports to list)

Each item gives the Care Compare API path that returns the report PDF. Medicare refuses cloud
servers, so the PDF has to be fetched from a browser on kg's computer (see pipeline/HARM_SUMMARIES.md).
"""
import json, os, re, sys
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
x = pd.read_excel(os.path.join(ROOT, "harm_summaries.xlsx"), dtype=str).fillna("")
x["ccn"] = x["ccn"].str.replace(".0", "", regex=False).str.zfill(6)
todo = x[x["what_happened"].str.strip() == ""].copy()
limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
out = []
for link, g in todo.groupby("report_link", sort=False):
    m = re.search(r"/health/([a-z-]+)\?date=(\d{4}-\d{2}-\d{2})", link)
    kind, date = (m.group(1), m.group(2)) if m else ("health-inspection", g["inspection_date"].iloc[0][:10])
    ccn = g["ccn"].iloc[0]
    out.append({"ccn": ccn, "facility": g["facility"].iloc[0], "inspection_date": g["inspection_date"].iloc[0][:10],
                "kind": kind, "report_link": link,
                "api_path": f"/api/care-compare/nursing-home/{ccn}/inspections/health/report/{kind}?date={date}",
                "citations": [{"tag": r.tag, "severity": r.severity, "cms_description": r.cms_description} for r in g.itertuples()]})
out.sort(key=lambda o: o["inspection_date"], reverse=True)
total = len(out)
if limit: out = out[:limit]
json.dump(out, sys.stdout, indent=1)
print()
print(f"# {len(todo)} citations without a summary, in {total} reports; listing {len(out)}", file=sys.stderr)
