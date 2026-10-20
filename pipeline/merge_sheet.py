#!/usr/bin/env python3
"""Pull your hand-written harm summaries from the Google Sheet and merge them into the repo copy.

Rule: a summary typed in the Sheet wins. A blank in the Sheet never erases a summary that is
already saved here. If the Sheet cannot be downloaded, the saved copy is used unchanged.
Usage: merge_sheet.py <sheet-export-url> <harm_summaries.xlsx>
"""
import io, sys, urllib.request
import pandas as pd

url, path = sys.argv[1], sys.argv[2]
mine = pd.read_excel(path, dtype=str).fillna("")
try:
    req = urllib.request.Request(url, headers={"User-Agent": "abc-ri-update/1.0"})
    data = urllib.request.urlopen(req, timeout=60).read()
    sheet = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
except Exception as e:
    print(f"NOTE: could not read the Google Sheet ({e}). Using the saved copy.")
    sys.exit(0)
need = {"ccn", "inspection_date", "tag", "what_happened", "summarized_by"}
if not need <= set(sheet.columns):
    print("NOTE: the Sheet does not have the expected columns. Using the saved copy.")
    sys.exit(0)
key = lambda d: d["ccn"].str.replace(".0", "", regex=False).str.zfill(6) + "|" + d["inspection_date"].str[:10] + "|" + d["tag"]
s = dict(zip(key(sheet), zip(sheet["what_happened"], sheet["summarized_by"])))
n = 0
for i, k in enumerate(key(mine)):
    new = s.get(k)
    if new and new[0].strip() and new[0] != mine.at[i, "what_happened"]:
        mine.at[i, "what_happened"], mine.at[i, "summarized_by"] = new
        n += 1
mine.to_excel(path, index=False, sheet_name="Harm citations")
print(f"Merged {n} summary change(s) from the Google Sheet.")
