# Saved data the monthly build reuses

The monthly update rebuilds `data.js` from CMS files. A few things on the site don't come from
those monthly files, so they are saved here and the build adds them back every time.

- `pbj_q1_2026.json`: staffing for each home from the CMS Payroll-Based Journal files for
  January to March 2026 (kg's upload of Oct 25, 2026). Any file named `pbj_<period>.json` here
  is added to `data.js` under that name. A newer quarter goes in as a new file; the page's
  "Q1 2026" wording in `index.html` would need updating to show it.
- `non_cms_homes.json`: the three licensed homes that aren't Medicare-certified and so aren't in
  CMS data (Brookdale Sakonnet Bay, Brookdale South Bay, RI Veterans Home). They are matched to
  rows in the facility extras sheet by name or RIDOH license number. Anything filled in on the
  sheet replaces what is saved here; a blank cell on the sheet keeps the saved value.

Closures are not stored here. They come from the notes column of the facility extras sheet:
a note starting "Closed <Month> <Year>" or "Closed <Year>" marks the home closed and shows its
data as of the last CMS file before it closed.
