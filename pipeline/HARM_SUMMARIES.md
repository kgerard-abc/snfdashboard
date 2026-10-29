# Harm citation summaries

Each harm citation (severity G to L) on the dashboard gets a short plain-language "what happened"
summary, written from the official CMS inspection report. A scheduled Claude run does this every
week and sends kg a pull request to review. Nothing is published until she merges it.

## Why it runs through kg's computer

Medicare refuses to send inspection report PDFs to cloud servers (Claude's workspace and GitHub's
runners both get HTTP 403), and ProPublica no longer carries the report text. The browser built into
the Claude desktop app on kg's computer can get them. So the run needs her computer on, the Claude
desktop app open, and medicare.gov allowed in that browser.

## Steps

1. Clone kgerard-abc/snfdashboard with push access.
2. If a pull request from a `harm-summaries-` branch is still open, stop and tell kg it is waiting.
3. `python3 pipeline/scripts/harm_todo.py --limit 25 > /tmp/todo.json` lists up to 25 reports with
   citations that have no summary, newest first, each with its `api_path`. Nothing listed: stop and
   report "No harm citations waiting for a summary."
4. In the Claude desktop app's browser (`Claude_Browser` tools), open
   `https://www.medicare.gov/care-compare/details/nursing-home/<ccn>/view-all/?state=RI` for the first
   report. If the site needs approval, call `request_access` for `https://www.medicare.gov` with scope
   `site`. If the browser can't be reached, stop and tell kg her computer or the Claude app looked
   offline, and that you'll try again next week.
5. On that page, run the snippet below once with `javascript_tool`, then call
   `await window.__getFindings('<api_path>', ['F0689', ...])` for each report with that report's tags.
   It returns the full findings text for each tag. An `error` means the report didn't download: skip it
   and list it in the pull request.
6. Write one summary per citation into a JSON file:
   `[{"ccn": "...", "inspection_date": "YYYY-MM-DD", "tag": "F0689", "what_happened": "..."}]`
7. `python3 pipeline/scripts/harm_apply.py that.json` writes them into `harm_summaries.xlsx` and adds them
   to the published `data.js` without rebuilding it. It never overwrites an existing summary. Do NOT run
   `update.py`: a rebuild belongs to the monthly update, and it would mix other data changes into this pull request.
8. Confirm only the summaries changed:
   `python3 -c "import json,subprocess;P=lambda t:json.loads(t[t.index('=')+1:].rstrip().rstrip(';'));a=P(subprocess.run(['git','show','HEAD:data.js'],capture_output=True,text=True).stdout);b=P(open('data.js').read());print(all(a[k]==b[k] for k in a if k!='harm_summaries') and set(a)==set(b))"` must print True.
9. Commit `data.js` and `pipeline/harm_summaries.xlsx` on a branch `harm-summaries-YYYY-MM-DD`, push, and
   open a pull request (see below). Never merge it and never push to main.

## Writing a summary

- Use only the findings text in the report. Every fact must be in it.
- One to three sentences, under 600 characters, in plain words a family member would understand.
  Say what happened to the resident or residents and the harm or danger, the way the existing summaries do.
- No names, no "Resident ID #1" style labels, no em dashes. Keep numbers, dates, and amounts as written.
- If the report says residents faced immediate jeopardy, the summary should make the danger clear.
- If the text is unclear or cut off, leave that citation out rather than guess, and list it in the pull request.

## Pull request

Title: `Harm citation summaries: N new (date)`. Body, plain language, no em dashes: a table of every new
summary (home, inspection date, tag, severity, summary, report link), then any reports that couldn't be
read, then how many citations are still waiting. End with: "Merging publishes these summaries. To change
one, comment here or edit it in the harm summaries Google Sheet, which always wins."

## The browser snippet

```js
window.__getFindings = async (apiPath, tags, maxChars = 14000) => {
  const r = await fetch(apiPath, {credentials: 'include'});
  const b = new Uint8Array(await r.arrayBuffer());
  const head = String.fromCharCode(...b.slice(0, 5));
  if (r.status !== 200 || head !== '%PDF-') return {error: `HTTP ${r.status}, not a PDF (${head})`};
  const pdfjs = await import('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.min.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.worker.min.mjs';
  const doc = await pdfjs.getDocument({data: b}).promise;
  let t = '';
  for (let p = 1; p <= doc.numPages; p++) t += (await (await doc.getPage(p)).getTextContent()).items.map(i => i.str).join(' ') + '\n';
  t = t.replace(/\s+/g, ' ');
  // drop the page headers the form repeats on every page
  t = t.replace(/\(continued on next page\).*?Residents Affected - (?:Few|Some|Many) (?:[A-Z][^.]*?\. )?(?=\S)/g, ' ');
  const marks = [...t.matchAll(/F ?(\d{4}) Level of Harm/g)].map(m => ({tag: 'F' + m[1], i: m.index}));
  const out = {pages: doc.numPages, tagsInReport: [...new Set(marks.map(m => m.tag))]};
  for (const tg of tags) {
    const first = marks.find(m => m.tag === tg);
    if (!first) { out[tg] = null; continue; }
    const next = marks.find(m => m.i > first.i && m.tag !== tg);
    out[tg] = t.slice(first.i, next ? next.i : undefined).slice(0, maxChars);
  }
  return out;
};
```
