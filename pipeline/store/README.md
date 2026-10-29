# Saved data the monthly build reuses

The monthly update rebuilds `data.js` from CMS files. A few things on the site don't come from
those monthly files, so they are saved here and the build adds them back every time.

- `pbj_qN_YYYY.json`: staffing for each home for one quarter, from CMS's daily Payroll-Based
  Journal files (contract staff share, weekday and weekend staffing, and the lowest-staffed day).
  Every Monday, `pipeline/fetch_pbj.py` checks CMS for a newer quarter and saves it here. The
  build adds every saved quarter to `data.js`, and the page shows the newest one. Q1 2026 came
  from kg's Oct 25, 2026 upload; recomputing it from CMS gives the same numbers.
- `non_cms_homes.json`: the three licensed homes that aren't Medicare-certified and so aren't in
  CMS data (Brookdale Sakonnet Bay, Brookdale South Bay, RI Veterans Home). They are matched to
  rows in the facility extras sheet by name or RIDOH license number. Anything filled in on the
  sheet replaces what is saved here; a blank cell on the sheet keeps the saved value.

Closures are not stored here. They come from the notes column of the facility extras sheet:
a note starting "Closed <Month> <Year>" or "Closed <Year>" marks the home closed and shows its
data as of the last CMS file before it closed.
