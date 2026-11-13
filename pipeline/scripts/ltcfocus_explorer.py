"""Build ltcfocus-explorer.json, the data behind the "Explore the LTCFocus data" page (#explore).

LTCFocus (Brown University School of Public Health, https://ltcfocus.org/) publishes yearly files
for every U.S. nursing home. This script keeps the Rhode Island homes and adds the state and U.S.
figures the page compares them with. Run it again when LTCFocus publishes a new year.

Usage:
    python3 pipeline/scripts/ltcfocus_explorer.py <folder with the LTCFocus downloads>

The folder needs these downloads (file names can have anything in front of them):
    facility_2011.xls ... facility_2022.xlsx, facility_2023_A.xlsx   one file per year
    accptid_crosswalk.xls                                             building ID to CMS number
    facility_privatepay_07_10.xls, _11_14.xls, _151.xls              private pay, 2007 to 2015
    state_2023_A.csv                                                  every state, 2023
    state_Pctpvtdays.xls                                              private pay by state, 2007 to 2015
    national_2011_2023.xlsx                                           U.S. figures by year

Notes on the data:
- "LNE" means 1 to 10 residents had the condition, so LTCFocus does not publish the number. It is
  kept as "f" (too few to show). "." means no figure and is kept as null.
- An acuity index of 0 means LTCFocus had no figure, so it is kept as null.
- LTCFocus gives some measures as proportions (0 to 1). They are turned into percents here.
- 2011 to 2014 files have no building ID; the crosswalk supplies it from the CMS number.
"""
import glob, json, math, os, re, sys
import pandas as pd

YEARS = list(range(2011, 2024))
PP_YEARS = list(range(2007, 2016))

# key, label, kind, source, definition, scale
# kind: pct (percent), num (number), yn (yes or no for a home; percent of homes for a group)
# source: insp, mds, adm, pay, qm, mcr, out (described in SOURCES below)
MEASURES = [
    # The home
    ("totbeds", "Beds", "num", "insp", "Certified beds, as reported at the home's annual inspection.", 1),
    ("nresid", "Residents on the first Thursday in April", "num", "mds", "Number of residents in the home that day.", 1),
    ("avg_dailycensus", "Average daily census", "num", "mcr", "Average number of residents in the home each day of the year.", 1),
    ("occpct", "Occupancy (%)", "pct", "insp", "Occupied beds as a share of all beds, at the home's annual inspection.", 1),
    ("profit", "For-profit", "yn", "insp", "Whether the home is run for profit. For a group of homes, the share of homes.", 1),
    ("multifac", "Part of a chain", "yn", "insp", "Whether the home is part of a chain. For a group of homes, the share of homes.", 1),
    ("hospbase", "Hospital-based", "yn", "insp", "Whether the home is part of a hospital. For a group of homes, the share of homes.", 1),
    ("alzunit", "Has a dementia (Alzheimer's) unit", "yn", "insp", "Whether the home reports a special care unit for dementia. For a group of homes, the share of homes.", 1),
    ("anyunit", "Has any special care unit", "yn", "insp", "Whether the home reports any special care unit, not counting ventilator units. For a group of homes, the share of homes.", 1),
    # Who pays
    ("paymcaid", "Medicaid main payer (% of residents)", "pct", "insp", "Residents whose care is paid mainly by Medicaid, at the home's annual inspection.", 1),
    ("paymcare", "Medicare main payer (% of residents)", "pct", "insp", "Residents whose care is paid mainly by Medicare, at the home's annual inspection.", 1),
    ("pcthmo", "Medicare Advantage (% of residents)", "pct", "mcr", "Residents in a Medicare Advantage plan on the first Thursday in April.", 1),
    ("pctpvtdays", "Private pay (% of resident days)", "pct", "mcr", "Share of the year's resident days that were private pay, from LTCFocus's Medicare and enrollment records. LTCFocus published this only for 2000 to 2015.", 1),
    # Who lives there
    ("avgage", "Average age", "num", "mds", "Average age of residents.", 1),
    ("pctunder65", "Under 65 (%)", "pct", "mds", "Residents younger than 65.", 1),
    ("pctfem", "Women (%)", "pct", "mds", "Residents who are women.", 1),
    ("pctwhite_mds3", "White (%)", "pct", "mds", "Residents recorded as White.", 1),
    ("pctblack_mds3", "Black (%)", "pct", "mds", "Residents recorded as Black.", 1),
    ("pcthisp_mds3", "Hispanic (%)", "pct", "mds", "Residents recorded as Hispanic.", 1),
    # Care needs
    ("acuindex2", "Acuity index", "num", "insp", "How much care the residents need, from counts the home reports at its inspection: help with daily activities and special treatments. Higher means more care.", 1),
    ("avgadl_mds3", "ADL score (0 to 28)", "num", "mds", "How much help residents need with daily activities like eating, moving, and using the toilet. 0 means no help, 28 means total help.", 1),
    ("pctlocare_mds3", "Low-care residents (%), 2011 to 2019", "pct", "mds", "Residents who need little help with daily activities. LTCFocus changed how it counts this in 2020.", 1),
    ("pctlocare_imp", "Low-care residents (%), 2020 on", "pct", "mds", "Residents who need little help with daily activities, counted LTCFocus's newer way.", 1),
    ("pctbedft_mds3", "Bedfast (%)", "pct", "mds", "Residents who stay in bed all or most of the time.", 1),
    ("pctwalking", "Walk in the hallway (%)", "pct", "mds", "Residents who can walk in the hallway.", 1),
    ("pctincont_bladr_mds3", "Bladder incontinence (%)", "pct", "mds", "Residents who are incontinent of urine.", 1),
    ("pctincont_bowel_mds3", "Bowel incontinence (%)", "pct", "mds", "Residents who are incontinent of bowel.", 1),
    ("pctcath_mds3", "Catheter (%)", "pct", "mds", "Residents with a urinary catheter.", 1),
    ("pctvent_mds3", "On a ventilator (%)", "pct", "mds", "Residents on a ventilator.", 1),
    # Health conditions
    ("pctalz_dem", "Alzheimer's or other dementia (%)", "pct", "mds", "Residents with Alzheimer's disease or another dementia.", 1),
    ("pctlowcfs", "Little or no memory and thinking problems (%)", "pct", "mds", "Residents whose cognition is intact or only a little impaired.", 1),
    ("pctmidcfs", "Moderate memory and thinking problems (%)", "pct", "mds", "Residents with mild or moderate cognitive impairment.", 1),
    ("pcthighcfs", "Severe memory and thinking problems (%)", "pct", "mds", "Residents with severe cognitive impairment.", 1),
    ("pctschiz_bipol", "Schizophrenia or bipolar disorder (%)", "pct", "mds", "Residents with schizophrenia or bipolar disorder.", 1),
    ("pctchf", "Heart failure (%)", "pct", "mds", "Residents with congestive heart failure.", 1),
    ("pcthyper", "High blood pressure (%)", "pct", "mds", "Residents with high blood pressure.", 1),
    ("pctobese", "Severe obesity (%)", "pct", "mds", "Residents with a body mass index of 35 or more.", 1),
    ("pctuti", "Urinary tract infection (%)", "pct", "mds", "Residents with a urinary tract infection.", 1),
    # Admissions
    ("adm_bed", "Admissions per bed", "num", "adm", "Admissions during the year divided by the number of beds. Higher means more short stays.", 1),
    ("agg_hosp", "Admitted from a hospital (%)", "pct", "adm", "Share of the year's admissions that came from a hospital.", 1),
    ("agg_comm", "Admitted from the community (%)", "pct", "adm", "Share of the year's admissions that came from home or elsewhere in the community.", 1),
    # Staffing, inspection records
    ("dchrppd", "Nurse staff hours per resident day, 2011 to 2018", "num", "insp", "Hours of RNs, LPNs, and nurse aides per resident per day, from the home's staffing report at its inspection.", 1),
    ("rnhrppd", "RN hours per resident day, 2011 to 2018", "num", "insp", "Registered nurse hours per resident per day, from the home's staffing report at its inspection.", 1),
    ("lpnhrppd", "LPN hours per resident day, 2011 to 2018", "num", "insp", "Licensed practical nurse hours per resident per day, from the home's staffing report at its inspection.", 1),
    ("cnahrppd", "Aide hours per resident day, 2011 to 2018", "num", "insp", "Nurse aide hours per resident per day, from the home's staffing report at its inspection.", 1),
    ("rn2nrs", "RN share of licensed nurses (%), 2011 to 2018", "pct", "insp", "RNs as a share of all RNs and LPNs, from the home's staffing report at its inspection.", 100),
    ("anymdex", "Nurse practitioner or physician assistant, 2011 to 2018", "yn", "insp", "Whether the home reported a nurse practitioner or physician assistant at its inspection. For a group of homes, the share of homes.", 1),
    # Staffing, payroll records
    ("dchprd_pbj", "Nurse staff hours per resident day, payroll, 2017 on", "num", "pay", "Paid hours of RNs, LPNs, and nurse aides per resident per weekday.", 1),
    ("rnhprd_pbj", "RN hours per resident day, payroll, 2017 on", "num", "pay", "Paid registered nurse hours per resident per weekday.", 1),
    ("lpnhprd_pbj", "LPN hours per resident day, payroll, 2017 on", "num", "pay", "Paid licensed practical nurse hours per resident per weekday.", 1),
    ("cnahprd_pbj", "Aide hours per resident day, payroll, 2017 on", "num", "pay", "Paid nurse aide hours per resident per weekday.", 1),
    ("rn2nrs_pbj", "RN share of licensed nurse hours (%), payroll, 2017 on", "pct", "pay", "RN hours as a share of RN and LPN hours.", 100),
    ("anymdex_pbj", "Nurse practitioner or physician assistant on payroll, 2019 on", "yn", "pay", "Whether the home paid a nurse practitioner or physician assistant at any time in the year. For a group of homes, the share of homes.", 1),
    # Quality and outcomes
    ("restrain", "Physically restrained (%)", "pct", "insp", "Residents physically restrained, as reported at the home's annual inspection.", 1),
    ("pctfall30_mds3", "Fell since admission or last assessment (%)", "pct", "mds", "Residents who had a fall since they arrived or since their last assessment.", 1),
    ("nhcpu_mds3", "Pressure ulcers, high-risk long-stay residents (%)", "pct", "qm", "Long-stay residents at high risk who have pressure ulcers (bed sores).", 1),
    ("nhcadl_mds3", "Long-stay residents needing more help with daily activities (%)", "pct", "qm", "Long-stay residents whose need for help with daily activities went up.", 1),
    ("nhcpain_mds3", "Long-stay residents with daily pain (%), 2011 to 2018", "pct", "qm", "Long-stay residents with moderate to severe pain.", 1),
    ("pctfluvax_in", "Flu shot given in this home (%)", "pct", "mds", "Residents who got a flu shot in this home.", 1),
    ("pctfluvax_out", "Flu shot, here or elsewhere (%)", "pct", "mds", "Residents who got a flu shot in this home or somewhere else.", 1),
    ("mds_hospptyr", "Hospital stays per resident year", "num", "out", "Hospital stays for every 365 days residents spent in the home. Not adjusted for how sick residents were.", 1),
    ("obs_rehosprate", "Rehospitalization rate (%)", "pct", "out", "Residents newly admitted from a hospital who went back to a hospital (LTCFocus's rehospitalization rate). Not adjusted.", 100),
    ("adj_rehosprate", "Rehospitalization rate, adjusted (%)", "pct", "out", "The same figure, adjusted by LTCFocus for how sick residents were when they arrived.", 100),
    ("obs_successfuldc", "Successful discharge to the community (%)", "pct", "out", "Residents newly admitted from a hospital who went home or elsewhere in the community within 100 days and had no nursing home stay in the 30 days after. Not adjusted.", 100),
    ("adj_successfuldc", "Successful discharge to the community, adjusted (%)", "pct", "out", "The same figure, adjusted by LTCFocus for how sick residents were when they arrived.", 100),
]

SOURCES = {
    "insp": "Inspection records (CASPER): reported by the home at its annual inspection by RIDOH for CMS.",
    "mds": "Resident assessments (MDS): residents in the home on the first Thursday in April.",
    "adm": "Resident assessments (MDS) of everyone admitted during the year.",
    "pay": "Payroll records (PBJ): the week with the first Thursday in April, except where noted.",
    "qm": "CMS quality measures (Care Compare), April to June.",
    "mcr": "Medicare and enrollment records (LTCFocus's Residential History File).",
    "out": "Resident assessments (MDS) for the whole year, linked by LTCFocus to hospital records.",
}

# U.S. and state columns that hold the same measure under another name
NAT_COL = {"cnahprd_pbj": "cnahrpd_pbj_nat"}
STA_SCALE = {"anymdex_pbj": 100}   # the state file gives this one as a proportion
SUM = {"totbeds", "nresid", "avg_dailycensus"}   # for a group of homes (or a state), these are totals
STA_COL = {"adj_rehosprate": "avg_adj_rehosp_sta", "obs_rehosprate": "avg_obs_rehosp_sta",
           "adj_successfuldc": "avg_adj_successfuldc_sta", "obs_successfuldc": "avg_obs_successfuldc_sta"}


def find(folder, pattern):
    hits = sorted(glob.glob(os.path.join(folder, "*" + pattern)))
    if not hits:
        sys.exit("Missing a download matching *%s in %s" % (pattern, folder))
    return hits[-1]


def read(path):
    if path.endswith(".csv"):
        df = pd.read_csv(path, dtype=str)
    else:
        df = pd.read_excel(path, dtype=str, engine="calamine")
    df.columns = [str(c).strip() for c in df.columns]
    return df.apply(lambda c: c.str.strip() if c.dtype == object or str(c.dtype) == "str" else c)


def val(v, scale=1, kind="num"):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    v = str(v).strip()
    if v in ("", ".", "nan"):
        return None
    if v == "LNE":
        return "f"
    if kind == "yn":
        return 1 if v.lower() in ("yes", "1", "y") else 0 if v.lower() in ("no", "0", "n") else None
    try:
        x = float(v) * scale
    except ValueError:
        return None
    return round(x, 3) if abs(x) < 10 else round(x, 2)


def title(s):
    s = " ".join(str(s or "").split()).title()
    s = re.sub(r"\bRi\b", "RI", s)
    s = re.sub(r"\bLlc\b", "LLC", s)
    for a, b in [(" Ii", " II"), ("'S", "'s"), (" Of ", " of "), (" And ", " and "), (" The ", " the "),
                 (" At ", " at "), (" On ", " on "), (" For ", " for ")]:
        s = s.replace(a, b)
    return s


def main(folder, out_path):
    cw = read(find(folder, "accptid_crosswalk.xls"))
    to_id = dict(zip(cw.PROV1680, cw.ACCPT_ID))
    keys = [m[0] for m in MEASURES]

    homes = {}   # building id -> record
    for y in YEARS:
        pat = "facility_%d_A.xlsx" % y if y == 2023 else "facility_%d*.xls*" % y
        df = read(find(folder, pat))
        lc = {c.lower(): c for c in df.columns}
        df = df[df[lc["state"]] == "RI"]
        for _, r in df.iterrows():
            g = lambda k: r[lc[k]] if k in lc else None
            ccn = g("prov1680")
            bid = g("accpt_id") or to_id.get(ccn, ccn)
            h = homes.setdefault(bid, {"id": bid, "ccn": ccn, "names": {}, "towns": {}, "y": {}})
            h["ccn"] = ccn
            h["names"][y] = title(g("prov0475"))
            h["towns"][y] = title(g("prov3225"))
            row = []
            for key, _, kind, _, _, scale in MEASURES:
                v = val(g(key), scale, kind)
                if key == "acuindex2" and v == 0:
                    v = None
                row.append(v)
            h["y"][str(y)] = row

    # private pay, 2007 to 2015 (separate LTCFocus files)
    pi = keys.index("pctpvtdays")
    pp = pd.concat([read(find(folder, p)) for p in ("facility_privatepay_07_10.xls", "facility_privatepay_11_14.xls", "facility_privatepay_151.xls")])
    pp = pp[pp.accpt_id.str.startswith("41")]
    for _, r in pp.iterrows():
        bid, y, v = r.accpt_id, int(r.year), val(r.Pctpvtdays)
        if bid not in homes:
            homes[bid] = {"id": bid, "ccn": bid, "names": {}, "towns": {}, "y": {}}
        row = homes[bid]["y"].setdefault(str(y), [None] * len(keys))
        row[pi] = v

    out_homes = []
    for bid, h in sorted(homes.items()):
        yrs = sorted(h["names"])
        rec = {"id": bid, "ccn": h["ccn"],
               "name": h["names"][yrs[-1]] if yrs else "",
               "town": h["towns"][yrs[-1]] if yrs else "",
               "y": {k: h["y"][k] for k in sorted(h["y"])}}
        others = sorted({n for n in h["names"].values() if n and n != rec["name"]})
        if others:
            rec["other_names"] = others
        out_homes.append(rec)

    # U.S. by year
    nat = read(find(folder, "national_2011_2023.xlsx"))
    nat = nat.rename(columns={nat.columns[0]: "year"})
    us = {}
    for key, _, kind, _, _, scale in MEASURES:
        col = NAT_COL.get(key, key + "_nat")
        if col in nat.columns:
            us[key] = {str(int(float(y))): val(v, scale) for y, v in zip(nat.year, nat[col]) if val(v, scale) is not None}

    # every state, 2023
    st = read(find(folder, "state_2023_A.csv"))
    states = {}
    for key, _, kind, _, _, scale in MEASURES:
        col = STA_COL.get(key, key + "_sta")
        if col in st.columns:
            states[key] = {s: val(v, STA_SCALE.get(key, scale)) for s, v in zip(st.state, st[col])}
    # private pay by state, 2007 to 2015
    sp = read(find(folder, "state_Pctpvtdays.xls"))
    pp_states = {}
    for s, y, v in zip(sp.state, sp.year, sp.Pctpvtdays_sta):
        pp_states.setdefault(str(int(float(y))), {})[s] = val(v)

    data = {
        "source": "LTCFocus, Brown University School of Public Health (ltcfocus.org)",
        "years": [str(y) for y in PP_YEARS[:4]] + [str(y) for y in YEARS],
        "sources": SOURCES,
        "measures": [dict({"key": k, "label": l, "kind": kd, "src": s, "def": d}, **({"sum": 1} if k in SUM else {}))
                     for k, l, kd, s, d, _ in MEASURES],
        "homes": out_homes,
        "us": us,
        "states2023": states,
        "pp_states": pp_states,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("Wrote %s: %d homes, %d measures, %d KB" % (out_path, len(out_homes), len(MEASURES), os.path.getsize(out_path) // 1024))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    here = os.path.dirname(os.path.abspath(__file__))
    main(sys.argv[1], os.path.join(here, "..", "..", "ltcfocus-explorer.json"))
