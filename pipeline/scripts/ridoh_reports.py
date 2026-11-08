#!/usr/bin/env python3
"""RIDOH inspection reports for nursing homes that CMS has no data on.

A few Rhode Island nursing homes are licensed by RIDOH but not certified by Medicare or
Medicaid, so CMS publishes no inspections for them. RIDOH still inspects them and posts the
reports in its public Google Drive folders (one "Annual Surveys" and one "Complaints
Investigations" folder per home). ABC-RI writes a plain-language summary of each report.

The master copy is pipeline/store/ridoh_nh_reports.json, keyed by RIDOH license number
(the dashboard's ridoh_license_no). This script checks it and writes ridoh-reports.js in the
repo root, which index.html loads. Run it after any change:

    python3 pipeline/scripts/ridoh_reports.py          # check, then write ridoh-reports.js
    python3 pipeline/scripts/ridoh_reports.py --check  # check only; also fails if ridoh-reports.js is stale

Each report: date (survey completed, YYYY-MM-DD), type, no_findings, tier (most_serious,
serious, minor, or null), headline, paragraphs, link. Each paragraph starts with RIDOH's tag or
tags ("M595: " or "M015/M016: "), then "Short plain title / What happened". Facts come from the
inspectors' findings column only, never from the home's own plan of correction. No resident or
staff names, no em dashes. Tier is ABC-RI's judgment using the nursing home immediate jeopardy
standard, the same as the assisted living site, and kg reviews every serious and most serious call.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "pipeline", "store", "ridoh_nh_reports.json")
OUT = os.path.join(ROOT, "ridoh-reports.js")

TYPES = {"Annual inspection", "Complaint investigation", "Annual inspection and complaint investigation",
         "Follow-up inspection", "Off-site review"}
TIERS = {"most_serious", "serious", "minor"}
TAG = re.compile(r"^M\d{3,4}(/M\d{3,4})*: [^/]+ / .+")
NOTES = re.compile(r"\?\)|\(\?|\bduplicate\b|\bTBD\b|\bna\b|\[doesn't say\]|\bcheck this\b", re.I)
LEVEL_WORDS = re.compile(r"\b(most serious|serious|minor)\b", re.I)
LINK = re.compile(r"^https://drive\.google\.com/file/d/[\w-]+/view$")


def problems(d):
    out = []
    seen_links = set()
    for lic, home in d["homes"].items():
        if not re.match(r"^LTC\d{5}$", lic):
            out.append(f"{lic}: key should be a RIDOH license number like LTC00774")
        dates = [r["date"] for r in home["reports"]]
        if dates != sorted(dates, reverse=True):
            out.append(f"{lic}: reports are not newest first")
        for r in home["reports"]:
            where = f"{home['name']} {r.get('date')}"
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", r.get("date", "")):
                out.append(f"{where}: date must be YYYY-MM-DD")
            if r.get("type") not in TYPES:
                out.append(f"{where}: unknown type {r.get('type')!r}")
            if not LINK.match(r.get("link", "")):
                out.append(f"{where}: link should be https://drive.google.com/file/d/<id>/view")
            elif r["link"] in seen_links:
                out.append(f"{where}: the same RIDOH file is linked twice")
            seen_links.add(r.get("link"))
            text = " ".join([r.get("headline", "")] + r.get("paragraphs", []))
            if "—" in text or "–" in text:
                out.append(f"{where}: has an em or en dash")
            if NOTES.search(text):
                out.append(f"{where}: looks like a working note: {NOTES.search(text).group(0)!r}")
            if LEVEL_WORDS.search(r.get("headline", "")):
                out.append(f"{where}: headline names a level; the page labels the level")
            if r.get("no_findings"):
                if r.get("tier") is not None or r.get("paragraphs"):
                    out.append(f"{where}: no_findings reports need tier null and no paragraphs")
                continue
            if r.get("tier") not in TIERS:
                out.append(f"{where}: tier must be one of {sorted(TIERS)}")
            if not r.get("paragraphs"):
                out.append(f"{where}: has findings but no paragraphs")
            for p in r.get("paragraphs", []):
                if not TAG.match(p):
                    out.append(f"{where}: finding must start 'M###: Title / What happened': {p[:50]!r}")
            if r.get("tier") in ("most_serious", "serious") and len(r.get("headline", "").split()) >= 12:
                out.append(f"{where}: headline must be under 12 words")
    return out


def render(d):
    keep = {lic: {"name": h["name"], "reports": h["reports"]} for lic, h in d["homes"].items()}
    return ("/* Built by pipeline/scripts/ridoh_reports.py from pipeline/store/ridoh_nh_reports.json. "
            "Do not edit by hand. */\nwindow.RIDOH_NH_REPORTS=" +
            json.dumps({"updated": d["updated"], "homes": keep}, ensure_ascii=False, separators=(",", ":")) + ";\n")


def main():
    d = json.load(open(SRC, encoding="utf-8"))
    bad = problems(d)
    js = render(d)
    if "--check" in sys.argv:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != js:
            bad.append("ridoh-reports.js is out of date: run python3 pipeline/scripts/ridoh_reports.py")
    for b in bad:
        print("ERROR:", b)
    if bad:
        sys.exit(1)
    if "--check" not in sys.argv:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(js)
        n = sum(len(h["reports"]) for h in d["homes"].values())
        print(f"Wrote ridoh-reports.js: {n} reports for {len(d['homes'])} homes.")
    else:
        print("RIDOH nursing home reports: OK")


if __name__ == "__main__":
    main()
