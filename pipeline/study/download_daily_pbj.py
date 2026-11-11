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
        try:
            rows = ri_rows(avail[(y, q)])
        except Exception as e:
            print(f"Q{q} {y}: could not download ({e}); skipped", flush=True); continue
        kept = 0
        for r0 in rows:
            r = {k.lower(): v for k, v in r0.items()}   # older quarters spell column names differently
            if str(r.get("state", "RI")).upper() != "RI": continue
            wd = str(r.get("workdate", ""))
            if len(wd) < 8: continue
            g = lambda k: num(r.get(k.lower()))
            w.writerow([str(r.get("provnum", "")).strip(), f"{wd[:4]}-{wd[4:6]}-{wd[6:8]}",
                        round(sum(g(f"Hrs_{c}") for c in NURSE_CATS), 2),
                        round(sum(g(f"Hrs_{c}") for c in RN), 2),
                        round(sum(g(f"Hrs_{c}_ctr") for c in NURSE_CATS), 2),
                        g("MDScensus")])
            kept += 1
        if rows and not kept:
            print(f"Q{q} {y}: columns not recognized: {sorted(rows[0])[:12]}", flush=True)
        n += kept
        print(f"Q{q} {y}: {kept} Rhode Island rows", flush=True)
print(f"Saved {n} rows from {len(avail)} quarters to {out}")
