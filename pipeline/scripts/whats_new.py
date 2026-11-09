"""Weekly "What's new" digest for kg, by email, as a trial (November 2026). Nothing here changes any site.

Lists what was added to the three ABC-RI sites in a date range, by comparing each repo's main branch now with
the same branch as of the start date (from git history, so nothing needs saving between runs), and drafts
social media posts about it. kg reads the digest to decide whether there's enough news for a page on the site.

Usage (each repo cloned with enough history to reach the start date, e.g. git fetch --depth=300 origin main):
  python3 pipeline/scripts/whats_new.py --dash . --sales ../snfsales --alf ../alf-inspections \
      --since 2026-11-06 --out digest.md

Sources (all already published on the sites):
  snfdashboard    data.js                               harm citations (severity G and up) and fines, from CMS
                  pipeline/store/ridoh_nh_reports.json  RIDOH reports for the homes CMS doesn't cover
  snfsales        sales.json                            pending sale applications and state approvals
  alf-inspections data/facilities.json                  RIDOH assisted living inspection reports
"""
import argparse, datetime as dt, json, re, subprocess

DASH = "https://snfdashboard.abc-ri.org/"
SALES = "https://snfsales.abc-ri.org/"
ALF = "https://alinspections.abc-ri.org/"
# Something older than this when it first shows up is history being filled in (a backfill), not news, so it is
# left out. CMS posts citations and fines months after the inspection, so they get longer.
WINDOW_DAYS = {"harm": 365, "fine": 365, "ridoh_nh": 120, "sale_pending": 365, "sale_decided": 120, "alf": 120}
ORDER = ["harm", "fine", "sale_pending", "sale_decided", "alf", "ridoh_nh"]


class Repo:
    """Reads a file from a repo's working tree (now) or from its main branch as of a date (then)."""
    def __init__(self, path, before=None):
        self.path, self.commit = path, None
        if before:
            ref = "origin/main" if self._git("rev-parse", "--verify", "-q", "origin/main") else "HEAD"
            self.commit = self._git("rev-list", "-1", "--before=" + before + "T00:00", ref)
            if not self.commit:
                raise SystemExit(f"{path}: no history back to {before}; fetch more (git fetch --depth=300 origin main)")

    def _git(self, *args):
        r = subprocess.run(["git", "-C", self.path, *args], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""

    def read(self, rel):
        if self.commit:
            r = subprocess.run(["git", "-C", self.path, "show", f"{self.commit}:{rel}"], capture_output=True, text=True)
            return r.stdout if r.returncode == 0 else None
        try:
            return open(f"{self.path}/{rel}", encoding="utf-8").read()
        except FileNotFoundError:
            return None


def js_object(text, var):
    i = text.index(var + "=") + len(var) + 1
    return json.JSONDecoder().raw_decode(text[i:].lstrip())[0]


def dlabel(iso):
    d = dt.date.fromisoformat(iso[:10])
    return d.strftime("%B ") + str(d.day) + d.strftime(", %Y")


def money(n):
    return "${:,.0f}".format(n)


# ---------- items, keyed so the same item always gets the same key

def place_names(html, facilities):
    """The town shown on the dashboard: the village's town, with the village in parentheses (index.html's own tables)."""
    def obj(name):
        m = re.search(r"const " + name + r"\s*=\s*(\{.*?\});", html or "", re.S)
        return json.loads(m.group(1)) if m else {}
    village, by_ccn = obj("VILLAGE_TOWN"), obj("TOWN_BY_CCN")
    out = {}
    for f in facilities:
        city = f.get("city") or ""
        town = by_ccn.get(f["ccn"]) or village.get(city) or city
        out[f["ccn"]] = f"{town} ({city})" if town != city else city
    return out


def items(dash, sales, alf):
    D = js_object(dash.read("data.js"), "window.RINH_DATA")
    fac = {f["ccn"]: f for f in D["facilities"]}
    place = place_names(dash.read("index.html"), D["facilities"])
    out = {c: {} for c in ORDER}
    out["_missing"] = set()
    for ccn, rows in D["citations"].items():
        f = fac.get(ccn)
        if not f:
            continue
        for r in rows:
            # same test as the dashboard's "Recent harm citations" page: health inspection, severity G or higher, current
            if r[2] in "GHIJKL" and r[5] == "H" and r[7]:
                key = f"{ccn}|{r[0]}|{r[1]}"
                out["harm"][key] = {"ccn": ccn, "home": f["name"], "town": place[ccn], "date": r[0], "sev": r[2],
                                    "ij": r[2] in "JKL", "complaint": bool(r[3]),
                                    "summary": D.get("harm_summaries", {}).get(key), "cited": (D["tags"].get(r[1]) or [""])[0]}
    for ccn, rows in D["penalties"].items():
        f = fac.get(ccn)
        if f:
            for r in rows:
                if r[1] == "Fine" and r[2]:
                    out["fine"][f"{ccn}|{r[0]}|{r[2]}"] = {"ccn": ccn, "home": f["name"], "town": place[ccn], "date": r[0], "amount": r[2]}
    t = dash.read("pipeline/store/ridoh_nh_reports.json")
    if not t:
        out["_missing"].add("ridoh_nh")
    if t:
        for lic, h in json.loads(t).get("homes", {}).items():
            for rep in h.get("reports", []):
                out["ridoh_nh"][f"{lic}|{rep['date']}|{rep.get('link','')}"] = {
                    "home": h.get("name", lic), "date": rep["date"], "type": rep.get("type", ""),
                    "headline": rep.get("headline", ""), "no_findings": bool(rep.get("no_findings"))}
    t = sales.read("sales.json")
    if not t:
        out["_missing"] |= {"sale_pending", "sale_decided"}
    if t:
        for ccn, rows in json.loads(t).get("homes", {}).items():
            f = fac.get(ccn, {})
            for r in rows:
                item = {"ccn": ccn, "home": f.get("name", ccn), "town": place.get(ccn, ""), "date": r["date"],
                        "buyer": r.get("buyer") or "a buyer not yet identified", "mgmt_start": r.get("mgmt_start")}
                if r.get("pending"):
                    out["sale_pending"][f"{ccn}|{r.get('buyer')}|pending"] = item
                else:
                    out["sale_decided"][f"{ccn}|{r.get('buyer')}|{r['date']}"] = item
    t = alf.read("data/facilities.json")
    if t:
        for f in json.loads(t):
            for rep in f.get("reports", []):
                out["alf"][f"{f['key']}|{rep['date']}|{rep.get('link','')}"] = {
                    "lic": f.get("license_no") or "", "name": f["name"], "town": f.get("city", ""), "date": rep["date"],
                    "type": rep.get("type", ""), "tier": rep.get("tier"), "no_findings": bool(rep.get("no_findings")),
                    "headline": rep.get("headline", "")}
    return out


# ---------- the digest

LVL = {"most_serious": "Most serious", "serious": "Serious", "minor": "Minor"}


def list_section(w):
    s = []
    def head(title, rows):
        if rows:
            s.extend(["", f"## {title} ({len(rows)})", ""] + rows)
    head("Nursing homes: harm and immediate jeopardy citations", [
        f"- **{x['home']}**, {x['town']}. {'Immediate jeopardy' if x['ij'] else 'Actual harm'} (severity {x['sev']}), "
        f"inspection {dlabel(x['date'])}{', complaint' if x['complaint'] else ''}. {x['summary'] or 'CMS cited: ' + x['cited']} "
        f"{DASH}#f-{x['ccn']}" for x in w["harm"]])
    head("Nursing homes: federal fines", [
        f"- **{x['home']}**, {x['town']}. {money(x['amount'])} fine, {dlabel(x['date'])}. {DASH}#f-{x['ccn']}" for x in w["fine"]])
    head("Nursing home sales: new applications", [
        f"- **{x['home']}**, {x['town']}. Buyer: {x['buyer']}. Filed {dlabel(x['date'])}."
        + (f" The buyer took over management on {dlabel(x['mgmt_start'])}." if x.get("mgmt_start") else "")
        + f" {SALES}#home={x['ccn']}" for x in w["sale_pending"]])
    head("Nursing home sales: approved by the state", [
        f"- **{x['home']}**, {x['town']}. Sale to {x['buyer']} approved {dlabel(x['date'])}. {SALES}#home={x['ccn']}" for x in w["sale_decided"]])
    head("Assisted living: new state inspection reports", [
        f"- **{x['name']}**, {x['town']}. {dlabel(x['date'])}"
        + (f", {x['type']}" if x["type"] else "") + ". "
        + ("No problems found." if x["no_findings"] else (f"{LVL.get(x['tier'], 'Finding')}: {x['headline']}." if x["tier"] else x["headline"] + "."))
        + f" {ALF}#{x['lic']}" for x in w["alf"]])
    head("Nursing homes Medicare doesn't cover: new state inspection reports", [
        f"- **{x['home']}**. {dlabel(x['date'])}" + (f", {x['type']}" if x["type"] else "") + ". "
        + ("No problems found." if x["no_findings"] else x["headline"] + ".") for x in w["ridoh_nh"]])
    return s


def draft_posts(w):
    """Plain, factual drafts built only from what the sites already say. kg edits and posts them herself."""
    posts, lines = [], []
    n_harm, n_ij = len(w["harm"]), sum(1 for x in w["harm"] if x["ij"])
    pl = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"
    if n_harm:
        lines.append(f"- {pl(n_harm, 'new harm citation')} at Rhode Island nursing homes"
                     + (f", {n_ij} of them immediate jeopardy, CMS's most serious level" if n_ij else ""))
    if w["fine"]:
        lines.append(f"- {pl(len(w['fine']), 'new federal fine')} totaling {money(sum(x['amount'] for x in w['fine']))}")
    if w["sale_pending"]:
        lines.append(f"- {pl(len(w['sale_pending']), 'new application')} to buy a nursing home")
    if w["sale_decided"]:
        lines.append(f"- {pl(len(w['sale_decided']), 'nursing home sale')} approved by the state")
    if w["alf"]:
        ms = sum(1 for x in w["alf"] if x["tier"] == "most_serious")
        lines.append(f"- {pl(len(w['alf']), 'new state inspection report')} for assisted living residences"
                     + (f", {ms} with a most serious finding" if ms else ""))
    if not lines:
        return []
    posts.append(("Weekly roundup (Facebook or LinkedIn)",
                  f"New on ABC-RI's public data sites about Rhode Island long-term care, {dlabel(w['since'])} to {dlabel(w['until'])}:\n\n"
                  + "\n".join(lines) + f"\n\nNursing homes: {DASH}\nSales: {SALES}\nAssisted living: {ALF}"))
    for x in w["harm"]:
        if x["ij"]:
            posts.append((f"Immediate jeopardy: {x['home']}",
                          f"CMS inspectors cited {x['home']} in {x['town']} at the immediate jeopardy level, their most serious, "
                          f"in an inspection on {dlabel(x['date'])}.\n\n{x['summary'] or 'CMS cited the home for this: ' + x['cited']}\n\n"
                          f"The home's full record, with a link to the inspection report: {DASH}#f-{x['ccn']}"))
    for x in w["sale_pending"]:
        extra = f" The buyer took over management of the home on {dlabel(x['mgmt_start'])}." if x.get("mgmt_start") else ""
        posts.append((f"Sale application: {x['home']}",
                      f"The state has an application to take over ownership of {x['home']} in {x['town']}. The buyer: {x['buyer']}.{extra} "
                      f"The state's Health Services Council reviews these applications, and the public can comment.\n\n"
                      f"The home's record and its owners over time: {SALES}#home={x['ccn']}"))
    for x in w["sale_decided"]:
        posts.append((f"Sale approved: {x['home']}",
                      f"The state approved the sale of {x['home']} in {x['town']} to {x['buyer']} ({dlabel(x['date'])}).\n\n"
                      f"The home's record and its owners over time: {SALES}#home={x['ccn']}"))
    for x in w["alf"]:
        if x["tier"] == "most_serious":
            posts.append((f"Assisted living: {x['name']}",
                          f"A state inspection of {x['name']} in {x['town']} on {dlabel(x['date'])} found: {x['headline']}.\n\n"
                          f"ABC-RI rates this finding most serious, the level nursing home inspections call immediate jeopardy. "
                          f"Our summary and RIDOH's original report: {ALF}#{x['lic']}"))
    return posts


def digest(w):
    total = sum(len(w[c]) for c in ORDER)
    out = [f"# What's new on ABC-RI's sites, {dlabel(w['since'])} to {dlabel(w['until'])}", "",
           f"{total} new item{'' if total == 1 else 's'}. This is a trial by email; nothing here is on the sites as a list."]
    if not total:
        out += ["", "Nothing new was added to the three sites in this period."]
        return "\n".join(out) + "\n"
    out += list_section(w)
    posts = draft_posts(w)
    out += ["", "# Draft posts", "", "Drafts only. Nothing has been posted. Check each against the site before posting, and edit freely."]
    for title, body in posts:
        out += ["", f"## {title}", "", body]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dash", default=".")
    ap.add_argument("--sales", required=True)
    ap.add_argument("--alf", required=True)
    ap.add_argument("--since", required=True, help="first day to include (YYYY-MM-DD)")
    ap.add_argument("--until", default=dt.date.today().isoformat(), help="last day to include (default today)")
    ap.add_argument("--out", help="write the digest here (Markdown); otherwise print it")
    a = ap.parse_args()

    now = items(Repo(a.dash), Repo(a.sales), Repo(a.alf))
    then = items(Repo(a.dash, a.since), Repo(a.sales, a.since), Repo(a.alf, a.since))
    until = dt.date.fromisoformat(a.until)
    w = {"since": a.since, "until": a.until}
    for c in ORDER:
        if c in then["_missing"]:   # the file didn't exist yet at the start date, so there is nothing to compare with
            w[c] = []
            continue
        new = [v for k, v in now[c].items() if k not in then[c]
               and (until - dt.date.fromisoformat(v["date"][:10])).days <= WINDOW_DAYS[c]]
        new.sort(key=lambda x: x["date"], reverse=True)
        w[c] = new
    w["harm"] = [x for x in w["harm"] if x["ij"]] + [x for x in w["harm"] if not x["ij"]]
    text = digest(w)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
    print(text if not a.out else f"Wrote {a.out}: " + ", ".join(f"{c} {len(w[c])}" for c in ORDER))


if __name__ == "__main__":
    main()
