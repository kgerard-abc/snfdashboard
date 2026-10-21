#!/usr/bin/env python3
"""Download the current CMS nursing home files and pack them into one zip,
the same shape update.py already reads (a zip of CSV files).

Uses CMS's public Provider Data catalog (no login needed):
  https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items

Writes pipeline/new_cms_zips/nursing-homes_<YYYY-MM-DD>.zip and prints the CMS month.
Exits 0 with "NOTHING NEW" when the month is already loaded. Exits 1 on any problem,
so the GitHub run fails loudly and emails you instead of publishing something wrong.
"""
import csv, io, json, os, re, sys, urllib.request, zipfile
from datetime import datetime

CATALOG = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items?show-reference-ids=false"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "new_cms_zips")
STORE = os.path.join(HERE, "store")

# file name fragments the pipeline understands (same list as rinh.CMS_FILES)
WANTED = ["ProviderInfo", "HealthCitations", "FireSafetyCitations", "Penalties", "Ownership",
          "MDS_QualityMeasures", "QualityMsr_MDS", "QualityMsrMDS", "ClaimsQualityMeasures",
          "QualityMsr_Claims", "QualityMsrClaims", "SurveyDates", "StateUSAverages", "CitationDescriptions"]
MUST_HAVE = ["ProviderInfo", "HealthCitations", "Penalties", "Ownership", "SurveyDates"]


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "abc-ri-update/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    return data if binary else data.decode("utf-8-sig", errors="replace")


def die(msg):
    print("ERROR:", msg)
    sys.exit(1)


def main(force=False):
    items = json.loads(get(CATALOG))
    picked, newest = {}, ""
    for i in items:
        for d in i.get("distribution", []) or []:
            if isinstance(d, dict) and isinstance(d.get("data"), dict):
                d = d["data"]            # the catalog nests the real entry under "data"
            if not isinstance(d, dict):
                continue
            url = d.get("downloadURL") or ""
            base = os.path.basename(url.split("?")[0])
            if not base.lower().endswith(".csv"):
                continue
            for frag in WANTED:
                if re.search(r"(^|_|-)" + re.escape(frag) + r"(_|\.|$)", base, re.I) or base.startswith(frag):
                    picked[base] = url
                    newest = max(newest, str(i.get("modified", ""))[:10])
                    break
    names = " ".join(picked)
    missing = [m for m in MUST_HAVE if m.lower() not in names.lower()]
    if missing:
        die(f"CMS catalog did not list these needed files: {missing}. Found: {sorted(picked)}")
    # which month is it? read it from the provider file itself
    prov = next(u for b, u in picked.items() if "providerinfo" in b.lower())
    head = get(prov)
    rows = csv.DictReader(io.StringIO(head))
    months = {}
    for n, r in enumerate(rows):
        key = next((k for k in r if k and k.lower().replace(" ", "_") in ("processing_date", "filedate")), None)
        if key and r[key]:
            m = r[key][:7] if re.match(r"\d{4}-\d{2}", r[key]) else datetime.strptime(r[key][:10], "%m/%d/%Y").strftime("%Y-%m") if "/" in r[key] else ""
            months[m] = months.get(m, 0) + 1
        if n > 300:
            break
    if not months:
        die("could not read the processing date from the CMS provider file")
    month = max(months, key=months.get)
    loaded = os.path.join(STORE, "releases_loaded.csv")
    if os.path.exists(loaded) and not force:
        have = {}
        for r in csv.DictReader(open(loaded)):
            have[r["cms_month"]] = r.get("loaded_on", "")
        if month in have and (not re.match(r"\d{4}-\d{2}-\d{2}", have[month]) or newest <= have[month]):
            print(f"NOTHING NEW: CMS month {month} is already loaded (CMS file dated {newest}).")
            return
    os.makedirs(OUT, exist_ok=True)
    zpath = os.path.join(OUT, f"nursing-homes_{newest or datetime.now().strftime('%Y-%m-%d')}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for base, url in sorted(picked.items()):
            z.writestr(base, get(url, binary=True))
            print("downloaded", base)
    print(f"READY: CMS month {month}, wrote {zpath}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
