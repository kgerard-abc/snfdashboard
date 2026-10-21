#!/usr/bin/env python3
"""Replace the saved facility_extras.xlsx with what is typed in the Google Sheet.

The Sheet is the master copy. If it cannot be downloaded, or looks wrong, the saved copy is
used unchanged and the run carries on.
Usage: merge_extras.py <sheet-export-url> <facility_extras.xlsx>
"""
import io, sys, urllib.request
import pandas as pd

url, path = sys.argv[1], sys.argv[2]
mine = pd.read_excel(path, sheet_name="Extras", dtype=str).fillna("")
try:
    req = urllib.request.Request(url, headers={"User-Agent": "abc-ri-update/1.0"})
    data = urllib.request.urlopen(req, timeout=60).read()
    book = pd.ExcelFile(io.BytesIO(data))
    name = "Extras" if "Extras" in book.sheet_names else book.sheet_names[0]
    sheet = book.parse(name, dtype=str).fillna("")
except Exception as e:
    print(f"NOTE: could not read the Google Sheet ({e}). Using the saved copy.")
    sys.exit(0)
missing = [c for c in mine.columns if c not in sheet.columns]
if missing:
    print(f"NOTE: the Sheet is missing these columns: {missing}. Using the saved copy.")
    sys.exit(0)
sheet = sheet.reindex(columns=list(mine.columns))
clean = lambda d: set(d["ccn"].str.replace(".0", "", regex=False).str.strip()) - {""}
lost = clean(mine) - clean(sheet)
if len(sheet) < len(mine) - 3 or len(lost) > 3:
    print(f"NOTE: the Sheet has {len(sheet)} rows against {len(mine)} saved, and drops {len(lost)} homes. Using the saved copy.")
    sys.exit(0)
changed = 0
if len(sheet) == len(mine):
    changed = int((sheet.reset_index(drop=True) != mine.reset_index(drop=True)).to_numpy().sum())
sheet.to_excel(path, index=False, sheet_name="Extras")
print(f"Took {len(sheet)} rows from the Google Sheet ({changed} cell change(s), {len(lost)} home(s) absent).")
