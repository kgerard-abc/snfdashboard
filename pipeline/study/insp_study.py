"""Does daily nurse staffing rise in the weeks before a standard inspection?
For each inspection: each day's nurse hours per resident (days under 1.5 = payroll gaps, dropped),
minus that home's usual level for the same weekday in the baseline weeks (5 to 12 weeks before and after).
Averaged by week relative to the inspection, compared with complaint inspections (not predictable)."""
import sys, numpy as np, pandas as pd

daily_path, surveys_path = sys.argv[1], sys.argv[2]
d = pd.read_csv(daily_path, dtype={"ccn": str})
d["date"] = pd.to_datetime(d.date)
d = d[d.census > 0]
d["h"] = d.nurse_hours / d.census
d["rn"] = d.rn_hours / d.census
d["ctr"] = d.contract_hours / d.census
d = d[d.h >= 1.5]
print("daily rows", len(d), d.date.min().date(), "to", d.date.max().date(), "homes", d.ccn.nunique())
by = {c: g.set_index("date").sort_index() for c, g in d.groupby("ccn")}

s = pd.read_csv(surveys_path, dtype=str)
s["date"] = pd.to_datetime(s.survey_date)
std = s[s.type_of_survey == "Health Standard"][["ccn", "date"]].drop_duplicates()
cmp_ = s[s.type_of_survey == "Health Complaint"][["ccn", "date"]].drop_duplicates()
# complaint surveys within 60 days of a standard one are left out of the comparison group
cmp_ = cmp_[[not ((std.ccn == c) & ((std.date - t).abs() <= pd.Timedelta(days=60))).any() for c, t in zip(cmp_.ccn, cmp_.date)]]

def event_curve(ev, col="h", weeks=8):
    rows = []
    for c, t in zip(ev.ccn, ev.date):
        g = by.get(c)
        if g is None: continue
        w = g.loc[t - pd.Timedelta(days=84): t + pd.Timedelta(days=84)]
        if len(w) < 120: continue
        off = (w.index - t).days
        base = w[(np.abs(off) >= 29)]
        if len(base) < 40: continue
        wdmean = base.groupby(base.index.weekday)[col].mean()
        res = w[col] - wdmean.reindex(w.index.weekday).values
        wk = np.floor(off / 7).astype(int)
        r = pd.DataFrame({"wk": wk, "res": res.values}).groupby("wk").res.mean()
        rows.append(r)
    R = pd.DataFrame(rows)
    out = pd.DataFrame({"mean": R.mean(), "se": R.std() / np.sqrt(R.count()), "n": R.count()})
    return out.loc[-weeks:weeks - 1], len(R)

for label, col in [("All nurse staff", "h"), ("RN", "rn"), ("Agency/contract", "ctr")]:
    for name, ev in [("Standard inspections", std), ("Complaint inspections (comparison)", cmp_)]:
        for period, lo, hi in [("all years", "2017-01-01", "2027-01-01"), ("2022 on", "2022-01-01", "2027-01-01")]:
            e = ev[(ev.date >= lo) & (ev.date < hi)]
            cur, n = event_curve(e, col)
            print(f"\n== {label}, {name}, {period}: {n} inspections (hours per resident per day vs that home's usual level; week 0 = the week starting on the inspection date)")
            for wk, r in cur.iterrows():
                print(f"  week {wk:+d}: {r['mean']:+.3f} (±{1.96*r['se']:.3f})")
