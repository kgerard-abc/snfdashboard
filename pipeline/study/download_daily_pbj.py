"""One-off study download (not part of the site build): every quarter of CMS daily nurse staffing
(Payroll-Based Journal) for Rhode Island, saved as one compact CSV for analysis.
Columns: ccn, date, nurse_hours, rn_hours, contract_hours, census."""
import csv, gzip, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fetch_pbj import available_quarters, ri_rows, num, NURSE_CATS

RN = ["RNDON", "RNadmin", "RN"]
out = sys.argv[1] if len(sys.argv) > 1 else "pbj_daily_ri.csv.gz"
avail = available_quarters()
n = 0
with gzip.open(out, "wt", newline="") as f:
    w = csv.writer(f); w.writerow(["ccn", "date", "nurse_hours", "rn_hours", "contract_hours", "census"])
    for (y, q) in sorted(avail):
        rows = ri_rows(avail[(y, q)])
        for r in rows:
            wd = str(r["WorkDate"])
            w.writerow([str(r["PROVNUM"]).strip(), f"{wd[:4]}-{wd[4:6]}-{wd[6:8]}",
                        round(sum(num(r.get(f"Hrs_{c}")) for c in NURSE_CATS), 2),
                        round(sum(num(r.get(f"Hrs_{c}")) for c in RN), 2),
                        round(sum(num(r.get(f"Hrs_{c}_ctr")) for c in NURSE_CATS), 2),
                        num(r.get("MDScensus"))])
        n += len(rows)
        print(f"Q{q} {y}: {len(rows)} Rhode Island rows", flush=True)
print(f"Saved {n} rows from {len(avail)} quarters to {out}")
