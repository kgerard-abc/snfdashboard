"""
Monthly update: add one (or more) CMS nursing home release zips to the database,
then rebuild the Excel workbook and the dashboard data.

Usage:
    python update.py                      (adds any new zips sitting in the new_cms_zips folder)
    python update.py path/to/nursing-homes_2026-11-06.zip [more zips...]

Get the zip from https://data.cms.gov/provider-data/archived-data/nursing-homes
(or the "Download all" link on the Nursing homes topic page).
Running the same month twice is safe: the newer copy just replaces the older one.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rinh  # noqa: E402
import build  # noqa: E402

ROOT = os.path.dirname(HERE)
STORE = os.path.join(ROOT, "store")


def main(paths):
    store = rinh.load_store(STORE)
    if not paths:
        # no files named: use every zip in the new_cms_zips folder that hasn't been loaded yet
        folder = os.path.join(ROOT, "new_cms_zips")
        done = set(store["releases_loaded"]["source"]) if store.get("releases_loaded") is not None else set()
        paths = sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".zip") and f not in done) \
            if os.path.isdir(folder) else []
        if not paths:
            print("No new CMS zips found in new_cms_zips. Rebuilding the workbook and dashboard from what's already loaded.")
    for p in paths:
        tables = rinh.filter_ri(rinh.read_release_zip(p))
        month = rinh.add_release(store, tables, os.path.basename(p))
        n = len(tables.get("providerinfo", []))
        print(f"Added CMS release for {month} from {os.path.basename(p)} ({n} RI facilities)")
    rinh.save_store(store, STORE)
    build.build_all(ROOT)


if __name__ == "__main__":
    main(sys.argv[1:])
