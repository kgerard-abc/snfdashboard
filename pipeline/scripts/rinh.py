"""
RI Nursing Home Database: core library.

The "store" folder holds the master database as plain CSV files, one per topic.
Each CMS monthly release is merged in by add_release(). Everything else
(Excel workbook, dashboard data) is generated from the store by build.py.
"""
import io
import os
import re
import zipfile
from datetime import datetime

import pandas as pd

STATE = "RI"

# CMS file name fragment -> our table name
CMS_FILES = {
    "ProviderInfo": "providerinfo",
    "HealthCitations": "healthcitations",
    "HealthDeficiencies": "healthcitations",
    "FireSafetyCitations": "firesafetycitations",
    "FireSafetyDeficiencies": "firesafetycitations",
    "Penalties": "penalties",
    "Ownership": "ownership",
    "QualityMsr_MDS": "qualitymsr_mds",
    "QualityMsrMDS": "qualitymsr_mds",
    "QualityMsr_Claims": "qualitymsr_claims",
    "QualityMsrClaims": "qualitymsr_claims",
    "SurveyDates": "surveydates",
    "StateUSAverages": "stateusaverages",
    "CitationDescriptions": "citationdescriptions",
}

# Old CMS column names -> current names (CMS renamed many columns over the years)
LEGACY = {
    "provnum": "cms_certification_number_ccn",
    "federal_provider_number": "cms_certification_number_ccn",
    "provname": "provider_name",
    "address": "provider_address",
    "city": "city_town",
    "provider_city": "city_town",
    "provider_state": "state",
    "zip": "zip_code",
    "provider_zip_code": "zip_code",
    "filedate": "processing_date",
    "affiliated_entity_name": "chain_name",
    "affiliated_entity_id": "chain_id",
    "survey_date_output": "survey_date",
    "surveytype": "survey_type",
    "defpref": "deficiency_prefix",
    "tag": "deficiency_tag_number",
    "tag_desc": "deficiency_description",
    "scope": "scope_severity_code",
    "defstat": "deficiency_corrected",
    "statdate": "correction_date",
    "cycle": "inspection_cycle",
    "standard": "standard_deficiency",
    "complaint": "complaint_deficiency",
    "category": "deficiency_category",
    "pnlty_date": "penalty_date",
    "pnlty_type": "penalty_type",
    "fine_amt": "fine_amount",
    "payden_strt_dt": "payment_denial_start_date",
    "payden_days": "payment_denial_length_in_days",
    "role_desc": "role_played_by_owner_or_manager_in_facility",
    "owner_percentage": "ownership_percentage",
    "provider_number_ccn": "cms_certification_number_ccn",
    # state averages legacy
    "restot": "average_number_of_residents_per_day",
    "tothrd": "reported_total_nurse_staffing_hours_per_resident_per_day",
    "rnhrd": "reported_rn_staffing_hours_per_resident_per_day",
    "aidhrd": "reported_nurse_aide_staffing_hours_per_resident_per_day",
    "vochrd": "reported_lpn_staffing_hours_per_resident_per_day",
    "totlichrd": "reported_licensed_staffing_hours_per_resident_per_day",
    "pthrd": "reported_physical_therapist_staffing_hours_per_resident_per_day",
    "cm_total": "case_mix_total_nurse_staffing_hours_per_resident_per_day",
    "cm_rn": "case_mix_rn_staffing_hours_per_resident_per_day",
    "fine_cnt": "number_of_fines",
    "fine_tot": "fine_amount_in_dollars",
    "c1_hlth_defs_cnt": "cycle_1_total_number_of_health_deficiencies",
}


def snake(c):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(c).lower())).strip("_")


def standardize(df):
    """snake_case the columns and fold legacy names into current names."""
    df = df.copy()
    df.columns = [snake(c) for c in df.columns]
    for old, new in LEGACY.items():
        if old in df.columns:
            if new in df.columns:
                df[new] = df[new].where(df[new].notna() & (df[new] != ""), df[old])
                df = df.drop(columns=[old])
            else:
                df = df.rename(columns={old: new})
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def to_month(s):
    d = pd.to_datetime(s, errors="coerce", format="mixed")
    return d.dt.strftime("%Y-%m")


def norm_date(s):
    d = pd.to_datetime(s, errors="coerce", format="mixed")
    return d.dt.strftime("%Y-%m-%d")


def norm_ccn(s):
    s = s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    return s.str.zfill(6)


# ---------------------------------------------------------------- readers

def read_release_zip(path):
    """Read one CMS monthly 'nursing-homes' zip and return {table: RI dataframe}."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.lower().endswith(".csv"):
                continue
            base = os.path.basename(name)
            table = None
            for frag, t in CMS_FILES.items():
                if re.search(r"(^|_|-)" + re.escape(frag) + r"(_|\.|$)", base, re.I) or base.startswith(frag):
                    table = t
                    break
            if table is None:
                continue
            with z.open(name) as f:
                raw = f.read()
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("cp1252", errors="replace")
            df = pd.read_csv(io.StringIO(text), dtype=str, low_memory=False)
            df = standardize(df)
            df["source_file"] = base
            out[table] = df
    return out


def filter_ri(tables):
    """Keep Rhode Island rows only (or RI + NATION for the averages table)."""
    res = {}
    for t, df in tables.items():
        if t == "stateusaverages":
            col = "state_or_nation" if "state_or_nation" in df.columns else "state"
            df = df[df[col].isin([STATE, "NATION", "Nation"])].copy()
            df["area"] = df[col].replace({"Nation": "NATION"})
        elif t == "citationdescriptions":
            pass
        else:
            if "state" in df.columns:
                df = df[df["state"] == STATE].copy()
            elif "cms_certification_number_ccn" in df.columns:
                df = df[df["cms_certification_number_ccn"].astype(str).str.startswith("41")].copy()
        res[t] = df
    return res


def release_month(tables):
    """The CMS 'processing date' month of a release, e.g. '2026-09'."""
    p = tables.get("providerinfo")
    if p is not None and "processing_date" in p.columns:
        m = to_month(p["processing_date"]).dropna()
        if len(m):
            return m.mode().iloc[0]
    for df in tables.values():
        if "processing_date" in df.columns:
            m = to_month(df["processing_date"]).dropna()
            if len(m):
                return m.mode().iloc[0]
    raise ValueError("Could not work out which month this CMS release is for.")


# ---------------------------------------------------------------- shaping each table

def _with_ccn(df):
    df = df.copy()
    src = "cms_certification_number_ccn" if "cms_certification_number_ccn" in df.columns else "ccn_std"
    df["ccn"] = norm_ccn(df[src])
    return df


PROVIDER_KEEP = [
    "provider_name", "legal_business_name", "provider_address", "city_town", "zip_code",
    "telephone_number", "county_parish", "urban", "ownership_type", "number_of_certified_beds",
    "average_number_of_residents_per_day", "provider_type", "provider_resides_in_hospital",
    "date_first_approved_to_provide_medicare_and_medicaid_services",
    "chain_name", "chain_id", "number_of_facilities_in_chain", "chain_average_overall_5_star_rating",
    "chain_average_health_inspection_rating", "chain_average_staffing_rating", "chain_average_qm_rating",
    "continuing_care_retirement_community", "special_focus_status", "sff", "abuse_icon", "high_performing_icon",
    "most_recent_health_inspection_more_than_2_years_ago", "provider_changed_ownership_in_last_12_months",
    "with_a_resident_and_family_council", "automatic_sprinkler_systems_in_all_required_areas",
    "overall_rating", "health_inspection_rating", "qm_rating", "long_stay_qm_rating", "short_stay_qm_rating",
    "staffing_rating", "rn_staffing_rating",
    "reported_nurse_aide_staffing_hours_per_resident_per_day", "reported_lpn_staffing_hours_per_resident_per_day",
    "reported_rn_staffing_hours_per_resident_per_day", "reported_licensed_staffing_hours_per_resident_per_day",
    "reported_total_nurse_staffing_hours_per_resident_per_day",
    "total_number_of_nurse_staff_hours_per_resident_per_day_on_the_weekend",
    "registered_nurse_hours_per_resident_per_day_on_the_weekend",
    "reported_physical_therapist_staffing_hours_per_resident_per_day",
    "total_nursing_staff_turnover", "registered_nurse_turnover", "number_of_administrators_who_have_left_the_nursing_home",
    "nursing_case_mix_index", "nursing_case_mix_index_ratio",
    "case_mix_total_nurse_staffing_hours_per_resident_per_day", "case_mix_rn_staffing_hours_per_resident_per_day",
    "exp_total", "exp_rn",
    "adjusted_total_nurse_staffing_hours_per_resident_per_day", "adjusted_rn_staffing_hours_per_resident_per_day",
    "rating_cycle_1_standard_survey_health_date", "rating_cycle_1_total_number_of_health_deficiencies",
    "rating_cycle_1_number_of_standard_health_deficiencies", "rating_cycle_1_number_of_complaint_health_deficiencies",
    "total_weighted_health_survey_score", "number_of_citations_from_infection_control_inspections",
    "number_of_fines", "total_amount_of_fines_in_dollars", "number_of_payment_denials", "total_number_of_penalties",
    "number_of_substantiated_complaints", "number_of_facility_reported_incidents",
    "latitude", "longitude", "processing_date",
]


def shape_provider(df, month):
    df = _with_ccn(df)
    for c in PROVIDER_KEEP:
        if c not in df.columns:
            df[c] = pd.NA
    out = df[["ccn"] + PROVIDER_KEEP].copy()
    # fold older equivalents
    out["case_mix_total_nurse_staffing_hours_per_resident_per_day"] = out[
        "case_mix_total_nurse_staffing_hours_per_resident_per_day"].fillna(out["exp_total"])
    out["case_mix_rn_staffing_hours_per_resident_per_day"] = out[
        "case_mix_rn_staffing_hours_per_resident_per_day"].fillna(out["exp_rn"])
    sff_old = out["sff"].map({"Y": "SFF"})
    out["special_focus_status"] = out["special_focus_status"].fillna(sff_old)
    out = out.drop(columns=["exp_total", "exp_rn", "sff"])
    out.insert(1, "cms_month", month)
    return out


CIT_KEEP = ["survey_date", "survey_type", "deficiency_prefix", "deficiency_tag_number", "deficiency_description",
            "deficiency_category", "scope_severity_code", "deficiency_corrected", "correction_date",
            "inspection_cycle", "standard_deficiency", "complaint_deficiency",
            "infection_control_inspection_deficiency", "citation_under_idr", "citation_under_iidr"]


def shape_citations(df, month):
    df = _with_ccn(df)
    for c in CIT_KEEP:
        if c not in df.columns:
            df[c] = pd.NA
    out = df[["ccn"] + CIT_KEEP].copy()
    out["survey_date"] = norm_date(out["survey_date"])
    out["correction_date"] = norm_date(out["correction_date"])
    out["deficiency_tag_number"] = out["deficiency_tag_number"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
    out["cms_month"] = month
    return out


def shape_penalties(df, month):
    df = _with_ccn(df)
    keep = ["penalty_date", "penalty_type", "fine_amount", "payment_denial_start_date", "payment_denial_length_in_days"]
    for c in keep:
        if c not in df.columns:
            df[c] = pd.NA
    out = df[["ccn"] + keep].copy()
    out["penalty_date"] = norm_date(out["penalty_date"])
    out["payment_denial_start_date"] = norm_date(out["payment_denial_start_date"])
    out["fine_amount"] = pd.to_numeric(out["fine_amount"], errors="coerce")
    out["cms_month"] = month
    # several identical fines on the same day are real; number them so they survive de-duplication
    # (amounts can change between releases, e.g. the 35% reduction for waiving a hearing,
    #  so the amount is not part of the record's identity)
    out = out.sort_values(["cms_month", "ccn", "penalty_date", "penalty_type", "fine_amount"])
    out["seq"] = out.groupby(["cms_month", "ccn", "penalty_date", "penalty_type"],
                             dropna=False).cumcount() + 1
    out["fine_amount"] = out["fine_amount"].map(lambda v: "" if pd.isna(v) else str(int(v)))
    return out


def shape_ownership(df, month):
    df = _with_ccn(df)
    keep = ["provider_name", "role_played_by_owner_or_manager_in_facility", "owner_type", "owner_name",
            "ownership_percentage", "association_date"]
    for c in keep:
        if c not in df.columns:
            df[c] = pd.NA
    out = df[["ccn"] + keep].copy()
    out = out.rename(columns={"role_played_by_owner_or_manager_in_facility": "role"})
    out["since"] = norm_date(out["association_date"].astype(str).str.replace("since ", "", regex=False))
    out = out.drop(columns=["association_date"])
    out["cms_month"] = month
    return out.drop_duplicates(["cms_month", "ccn", "role", "owner_name"])


def _quarter_add(q, n):
    y, k = int(q[:4]), int(q[-1])
    idx = y * 4 + (k - 1) + n
    return f"{idx // 4}Q{idx % 4 + 1}"


def shape_qm_mds(df, month):
    df = _with_ccn(df)
    df["cms_month"] = month
    q1 = df["q1_quarter"] if "q1_quarter" in df.columns else pd.Series(pd.NA, index=df.index)
    mp = df["measure_period"] if "measure_period" in df.columns else pd.Series(pd.NA, index=df.index)
    start = q1.where(q1.astype(str).str.match(r"^\d{4}Q\d$"), mp.astype(str).str[:6])
    start = start.where(start.astype(str).str.match(r"^\d{4}Q\d$"))
    frames = []
    for i in range(4):
        col = f"q{i + 1}_measure_score"
        if col not in df.columns:
            continue
        x = pd.DataFrame({"ccn": df["ccn"], "measure_code": df["measure_code"].astype(str),
                          "quarter": start.map(lambda q: _quarter_add(q, i) if isinstance(q, str) else pd.NA),
                          "score": pd.to_numeric(df[col], errors="coerce"), "cms_month": df["cms_month"]})
        frames.append(x)
    out = pd.concat(frames, ignore_index=True).dropna(subset=["score", "quarter"])
    out["score"] = out["score"].round(4)
    return out


def shape_qm_claims(df, month):
    df = _with_ccn(df)
    keep = ["measure_code", "measure_period", "adjusted_score", "observed_score", "expected_score"]
    for c in keep:
        if c not in df.columns:
            df[c] = pd.NA
    out = df[["ccn"] + keep].copy()
    out["measure_code"] = out["measure_code"].astype(str)
    for c in ["adjusted_score", "observed_score", "expected_score"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["adjusted_score"])
    out["cms_month"] = month
    return out


def shape_measures(mds, claims):
    frames = []
    for df in (mds, claims):
        if df is None:
            continue
        cols = [c for c in ["measure_code", "measure_description", "resident_type",
                            "used_in_quality_measure_five_star_rating"] if c in df.columns]
        x = df[cols].copy()
        x["measure_code"] = x["measure_code"].astype(str)
        frames.append(x.drop_duplicates("measure_code"))
    return pd.concat(frames) if frames else None


AVG_KEEP = [
    "average_number_of_residents_per_day",
    "reported_total_nurse_staffing_hours_per_resident_per_day", "reported_rn_staffing_hours_per_resident_per_day",
    "reported_lpn_staffing_hours_per_resident_per_day", "reported_nurse_aide_staffing_hours_per_resident_per_day",
    "total_number_of_nurse_staff_hours_per_resident_per_day_on_the_weekend",
    "registered_nurse_hours_per_resident_per_day_on_the_weekend",
    "case_mix_total_nurse_staffing_hours_per_resident_per_day",
    "total_nursing_staff_turnover", "registered_nurse_turnover", "number_of_administrators_who_have_left_the_nursing_home",
    "nursing_case_mix_index", "number_of_fines", "fine_amount_in_dollars",
    "cycle_1_total_number_of_health_deficiencies",
    "overall_rating", "health_inspection_rating", "qm_rating", "staffing_rating",
    "percentage_of_long_stay_residents_who_received_an_antipsychotic_medication",
    "percentage_of_long_stay_residents_experiencing_one_or_more_falls_with_major_injury",
    "percentage_of_long_stay_residents_with_pressure_ulcers",
    "percentage_of_high_risk_long_stay_residents_with_pressure_ulcers",
    "percentage_of_short_stay_residents_who_were_rehospitalized_after_a_nursing_home_admission",
    "number_of_hospitalizations_per_1000_long_stay_resident_days",
]


def shape_averages(df, month):
    df = df.copy()
    if "area" not in df.columns:
        col = "state_or_nation" if "state_or_nation" in df.columns else "state"
        df["area"] = df[col]
    for c in AVG_KEEP:
        if c not in df.columns:
            df[c] = pd.NA
    out = df[["area"] + AVG_KEEP].copy()
    out["pressure_ulcers_long_stay"] = out["percentage_of_long_stay_residents_with_pressure_ulcers"].fillna(
        out["percentage_of_high_risk_long_stay_residents_with_pressure_ulcers"])
    out = out.drop(columns=["percentage_of_long_stay_residents_with_pressure_ulcers",
                            "percentage_of_high_risk_long_stay_residents_with_pressure_ulcers"])
    out.insert(0, "cms_month", month)
    return out


def shape_surveydates(df, month):
    df = _with_ccn(df)
    keep = ["survey_date", "type_of_survey", "survey_cycle"]
    for c in keep:
        if c not in df.columns:
            df[c] = pd.NA
    out = df[["ccn"] + keep].copy()
    out["survey_date"] = norm_date(out["survey_date"])
    out["cms_month"] = month
    return out


def shape_tags(df):
    keep = ["deficiency_prefix", "deficiency_tag_number", "deficiency_description", "deficiency_category"]
    for c in keep:
        if c not in df.columns:
            df[c] = pd.NA
    out = df[keep].copy()
    out["deficiency_tag_number"] = out["deficiency_tag_number"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
    return out


# ---------------------------------------------------------------- store

STORE_FILES = {
    "provider_monthly": ["ccn", "cms_month"],
    "health_citations": ["ccn", "survey_date", "deficiency_prefix", "deficiency_tag_number"],
    "fire_citations": ["ccn", "survey_date", "deficiency_prefix", "deficiency_tag_number"],
    "penalties": ["ccn", "penalty_date", "penalty_type", "seq"],
    "ownership": ["ccn", "role", "owner_name"],
    "qm_mds": ["ccn", "measure_code", "quarter"],
    "qm_claims": ["ccn", "measure_code", "measure_period"],
    "measures": ["measure_code"],
    "state_us_averages": ["cms_month", "area"],
    "survey_dates": ["ccn", "survey_date", "type_of_survey"],
    "tags": ["deficiency_prefix", "deficiency_tag_number"],
}
# tables where we track when a record first and last appeared in CMS releases
TRACK_SEEN = {"health_citations", "fire_citations", "penalties", "ownership", "survey_dates"}


def load_store(store_dir):
    s = {}
    for name in STORE_FILES:
        p = os.path.join(store_dir, name + ".csv")
        s[name] = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[""]) if os.path.exists(p) else None
    p = os.path.join(store_dir, "releases_loaded.csv")
    s["releases_loaded"] = pd.read_csv(p, dtype=str) if os.path.exists(p) else None
    return s


def save_store(store, store_dir):
    os.makedirs(store_dir, exist_ok=True)
    for name, df in store.items():
        if df is not None:
            df.to_csv(os.path.join(store_dir, name + ".csv"), index=False)


def merge_table(name, old, new):
    """Combine stored rows with new rows. The newest version of each record wins.
    For event tables, keep first_seen / last_seen release months."""
    if new is None or len(new) == 0:
        return old
    key = STORE_FILES[name]
    new = new.copy()
    for k in key:
        new[k] = new[k].astype(str)
    if name in TRACK_SEEN:
        new["first_seen"] = new["cms_month"]
        new["last_seen"] = new["cms_month"]
    frames = [f for f in (old, new) if f is not None]
    allr = pd.concat([f.astype(str).replace({"nan": pd.NA, "<NA>": pd.NA, "None": pd.NA, "": pd.NA, "NaT": pd.NA}) for f in frames],
                     ignore_index=True)
    sort_col = "cms_month" if "cms_month" in allr.columns else None
    if sort_col:
        allr = allr.sort_values(sort_col, kind="stable")
    if name in TRACK_SEEN:
        fs = allr.groupby(key, dropna=False)["first_seen"].min()
        ls = allr.groupby(key, dropna=False)["last_seen"].max()
    allr = allr.drop_duplicates(key, keep="last")
    if name in TRACK_SEEN:
        allr = allr.set_index(key)
        allr["first_seen"] = fs
        allr["last_seen"] = ls
        allr = allr.reset_index()
    return allr.reset_index(drop=True)


def add_release(store, tables, label=""):
    """Merge one CMS release (already filtered to RI) into the store."""
    month = release_month(tables)
    t = tables
    pieces = {
        "provider_monthly": shape_provider(t["providerinfo"], month) if "providerinfo" in t else None,
        "health_citations": shape_citations(t["healthcitations"], month) if "healthcitations" in t else None,
        "fire_citations": shape_citations(t["firesafetycitations"], month) if "firesafetycitations" in t else None,
        "penalties": shape_penalties(t["penalties"], month) if "penalties" in t else None,
        "ownership": shape_ownership(t["ownership"], month) if "ownership" in t else None,
        "qm_mds": shape_qm_mds(t["qualitymsr_mds"], month) if "qualitymsr_mds" in t else None,
        "qm_claims": shape_qm_claims(t["qualitymsr_claims"], month) if "qualitymsr_claims" in t else None,
        "measures": shape_measures(t.get("qualitymsr_mds"), t.get("qualitymsr_claims")),
        "state_us_averages": shape_averages(t["stateusaverages"], month) if "stateusaverages" in t else None,
        "survey_dates": shape_surveydates(t["surveydates"], month) if "surveydates" in t else None,
        "tags": shape_tags(t["citationdescriptions"]) if "citationdescriptions" in t else None,
    }
    for name, df in pieces.items():
        store[name] = merge_table(name, store.get(name), df)
    rl = store.get("releases_loaded")
    row = pd.DataFrame([{"cms_month": month, "source": label,
                         "loaded_on": datetime.now().strftime("%Y-%m-%d"),
                         "facilities": str(len(t.get("providerinfo", [])))}])
    rl = pd.concat([rl, row]) if rl is not None else row
    store["releases_loaded"] = rl.drop_duplicates("cms_month", keep="last").sort_values("cms_month")
    return month
