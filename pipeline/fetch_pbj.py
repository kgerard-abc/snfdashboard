"""Add each new quarter of CMS daily staffing data (Payroll-Based Journal) for Rhode Island.

CMS posts the "Payroll Based Journal Daily Nurse Staffing" files one quarter at a time, a few
months after the quarter ends. For every quarter newer than the newest one saved in
pipeline/store/pbj_qN_YYYY.json, this downloads the Rhode Island rows and saves one file per
quarter. The build adds every saved quarter to data.js, and the page shows the newest one.

  python3 pipeline/fetch_pbj.py             add any new quarters (prints "NOTHING NEW" if none)
  python3 pipeline/fetch_pbj.py --check Q1 2026
                                            recompute a saved quarter and compare (changes nothing)

Per home and quarter (the same formulas as the original Q1 2026 numbers):
  contract_pct      contract or agency share of all nurse staff hours
  weekday_hprd      nurse staff hours per resident per day, Monday to Friday
  weekend_hprd      the same for Saturday and Sunday
  weekend_drop_pct  how much lower the weekend figure is than the weekday figure
  worst_day_hprd / worst_day_date   the single lowest-staffed day
Nurse staff hours = RN director of nursing, RN admin, RN, LPN admin, LPN, aides, aides in
training, and medication aides.
"""
import datetime
import glob
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_cms import get, die  # browser-style request with retries

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "store")
CATALOG = "https://data.cms.gov/data.json"
TITLE = "Payroll Based Journal Daily Nurse Staffing"
NURSE_CATS = ["RNDON", "RNadmin", "RN", "LPNadmin", "LPN", "CNA", "NAtrn", "MedAide"]
PAGE = 5000


def saved_quarters():
    out = []
    for p in glob.glob(os.path.join(STORE, "pbj_q[1-4]_[0-9][0-9][0-9][0-9].json")):
        m = re.search(r"pbj_q(\d)_(\d{4})\.json$", p)
        out.append((int(m.group(2)), int(m.group(1))))
    return sorted(out)


def available_quarters():
    """(year, quarter) -> API data URL, from CMS's catalog. CMS lists each quarter as its own
    entry, titled "Payroll Based Journal Daily Nurse Staffing : <a date>"."""
    cat = json.loads(get(CATALOG))
    out = {}
    for d in cat.get("dataset", []):
        if d.get("title", "").split(" : ")[0].strip().lower() != TITLE.lower():
            continue
        for dist in d.get("distribution", []):
            url = dist.get("accessURL") or ""
            if dist.get("format", "").upper() != "API" or "/data-api/" not in url:
                continue
            t = dist.get("temporal") or d.get("temporal") or ""
            start = t[0].get("startDate", "") if isinstance(t, list) and t and isinstance(t[0], dict) else str(t).split("/")[0]
            if not re.match(r"\d{4}-\d{2}-\d{2}", start):
                continue
            y, mo = int(start[:4]), int(start[5:7])
            out[(y, (mo - 1) // 3 + 1)] = url
    if not out:
        die(f"CMS's catalog has no quarterly API links for '{TITLE}'")
    return out


def ri_rows(url):
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"filter[STATE]": "RI", "size": PAGE, "offset": offset})
        page = json.loads(get(f"{url}?{q}"))
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def summarize(rows):
    by_home = {}
    for r in rows:
        if str(r.get("STATE", "RI")).upper() != "RI":
            continue
        wd = str(r["WorkDate"])
        day = datetime.date(int(wd[:4]), int(wd[4:6]), int(wd[6:8]))
        by_home.setdefault(str(r["PROVNUM"]).strip(), []).append(dict(
            total=sum(num(r.get(f"Hrs_{c}")) for c in NURSE_CATS),
            ctr=sum(num(r.get(f"Hrs_{c}_ctr")) for c in NURSE_CATS),
            census=num(r.get("MDScensus")), day=day))

    def hprd(rs):
        h, c = sum(x["total"] for x in rs), sum(x["census"] for x in rs)
        return round(h / c, 3) if c else None

    out = {}
    for ccn, rs in sorted(by_home.items()):
        th, tc = sum(x["total"] for x in rs), sum(x["ctr"] for x in rs)
        wd_h = hprd([x for x in rs if x["day"].weekday() < 5])
        we_h = hprd([x for x in rs if x["day"].weekday() >= 5])
        daily = sorted((round(x["total"] / x["census"], 2), x["day"].isoformat()) for x in rs if x["census"] > 0)
        out[ccn] = {
            "contract_pct": round(tc / th * 100, 1) if th else None,
            "weekday_hprd": wd_h,
            "weekend_hprd": we_h,
            "weekend_drop_pct": round((1 - we_h / wd_h) * 100, 1) if (wd_h and we_h) else None,
            "worst_day_hprd": daily[0][0] if daily else None,
            "worst_day_date": daily[0][1] if daily else None,
        }
    return out


def main():
    avail = available_quarters()
    print("CMS has daily staffing quarters", ", ".join(f"Q{q} {y}" for y, q in sorted(avail)[-4:]), "(newest four shown)")

    if len(sys.argv) >= 4 and sys.argv[1] == "--check":
        y, q = int(sys.argv[3]), int(sys.argv[2].upper().lstrip("Q"))
        new = summarize(ri_rows(avail[(y, q)]))
        old = json.load(open(os.path.join(STORE, f"pbj_q{q}_{y}.json")))
        diff = [(c, k, old.get(c, {}).get(k), new.get(c, {}).get(k)) for c in sorted(set(old) | set(new))
                for k in ("contract_pct", "weekday_hprd", "weekend_hprd", "weekend_drop_pct", "worst_day_hprd", "worst_day_date")
                if old.get(c, {}).get(k) != new.get(c, {}).get(k)]
        print(f"Q{q} {y}: saved {len(old)} homes, recomputed {len(new)}, {len(diff)} value(s) differ")
        for d in diff[:15]:
            print("  differs:", *d)
        sys.exit(1 if diff else 0)

    have = saved_quarters()
    newest = have[-1] if have else (0, 0)
    todo = [k for k in sorted(avail) if k > newest]
    if not todo:
        print(f"NOTHING NEW: the newest saved quarter is Q{newest[1]} {newest[0]}")
        return
    for y, q in todo:
        homes = summarize(ri_rows(avail[(y, q)]))
        if len(homes) < 40:   # Rhode Island has about 70 homes; a short file means something went wrong
            die(f"Q{q} {y} has staffing for only {len(homes)} Rhode Island homes; not saving it")
        with open(os.path.join(STORE, f"pbj_q{q}_{y}.json"), "w", encoding="utf-8") as f:
            json.dump(homes, f, indent=0, sort_keys=True)
        print(f"Added staffing for Q{q} {y}: {len(homes)} Rhode Island homes")


if __name__ == "__main__":
    main()
