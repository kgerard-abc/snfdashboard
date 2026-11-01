/* English / Spanish toggle for the ABC-RI sites.

   How it works: the page is built in English by its own script. This file translates the
   finished page by looking up each piece of visible text in a phrase table (RINH_ES, in
   i18n-es.js). Nothing here changes the data or the page's own logic. The visitor's choice
   is remembered in this browser. Text that is not in the table (facility names, owner names,
   and for now the inspection tag descriptions and harm summaries) stays in English.

   Phrase table format:  "English phrase": "Spanish phrase"
   Placeholders in a key match values in the page text and carry over to the Spanish side:
     {n}  a number            {$}  a dollar amount        {D}  a date like "Oct 2026" or "Jun 20, 2025"
   Placeholders are copied across in order. Write {1}, {2}, ... on the Spanish side to reorder them.
   Short phrases (12 characters or fewer) only match when they are the whole text of an element. */
(function () {
  "use strict";
  var KEY = "rinh-lang";
  var TABLE = window.RINH_ES || {};
  var lang = "en";
  try { var saved = localStorage.getItem(KEY); if (saved === "es" || saved === "en") lang = saved; } catch (e) {}

  var MON_EN = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec";
  var MON_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  var MON_IDX = {}; MON_EN.split("|").forEach(function (m, i) { MON_IDX[m] = i; });
  var DATE_RE_SRC = "(?:" + MON_EN + ")\\s(?:\\d{1,2},\\s)?\\d{4}";
  var PH = {
    "{n}": "(\\d+(?:[.,]\\d+)*)",
    "{$}": "(\\$[\\d,.]+)",
    "{D}": "(" + DATE_RE_SRC + ")",
    "{*}": "(.+?)"
  };
  var TOKEN_RE = /\{n\}|\{\$\}|\{D\}|\{\*\}/g;

  function esDate(s) {
    var m = /^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s(?:(\d{1,2}),\s)?(\d{4})$/.exec(s);
    if (!m) return s;
    return (m[2] ? m[2] + " " : "") + MON_ES[MON_IDX[m[1]]] + " " + m[3];
  }
  function esVal(token, v) { return token === "{D}" ? esDate(v) : v; }
  function esc(s) { return s.replace(/[.*+?^$()|[\]\\]/g, "\\$&"); }

  // Every key in the table is the complete text of one piece of the page (a whole text node, or one
  // piece of a node that is split at " \u00b7 "). Matching whole pieces only means a phrase can never fire
  // inside someone else's text, such as an inspector's description of what happened.
  var exact = Object.create(null), pats = [];
  Object.keys(TABLE).forEach(function (en) {
    var tokens = en.match(TOKEN_RE);
    if (!tokens) { exact[en] = TABLE[en]; return; }
    var src = "", last = 0, re = new RegExp(TOKEN_RE.source, "g"), m;
    while ((m = re.exec(en))) { src += esc(en.slice(last, m.index)) + PH[m[0]]; last = m.index + m[0].length; }
    src += esc(en.slice(last));
    pats.push({ len: en.length, re: new RegExp("^" + src + "$"), tokens: tokens, es: TABLE[en] });
  });
  pats.sort(function (a, b) { return b.len - a.len; });

  function fill(rule, caps) {
    var out = rule.es, seq = 0;
    if (/\{\d\}/.test(out)) {
      return out.replace(/\{(\d)\}/g, function (_, i) { var k = +i - 1; return esVal(rule.tokens[k], caps[k]); });
    }
    return out.replace(TOKEN_RE, function () { var k = seq++; return esVal(rule.tokens[k], caps[k]); });
  }

  function piece(seg) {
    var e = exact[seg];
    if (e !== undefined) return e;
    for (var i = 0; i < pats.length; i++) {
      var m = pats[i].re.exec(seg);
      if (m) return fill(pats[i], m.slice(1));
    }
    return null;
  }

  // a bare date or date range ("Aug 2025", "Jan 2019 \u2013 now") that has no entry of its own
  var DATE_ONLY = new RegExp("^(" + DATE_RE_SRC + ")(?:\\s*[\\u2013-]\\s*(?:(" + DATE_RE_SRC + ")|now))?$");
  function bareDate(seg) {
    var m = DATE_ONLY.exec(seg);
    if (!m) return null;
    return esDate(m[1]) + (m[2] ? " \u2013 " + esDate(m[2]) : /now$/.test(seg) ? " \u2013 actualidad" : "");
  }

  function translate(text) {
    if (!text || !/[A-Za-z]/.test(text)) return text;
    var lead = /^\s*/.exec(text)[0], trail = /\s*$/.exec(text)[0];
    var core = text.slice(lead.length, text.length - trail.length);
    var whole = piece(core);
    if (whole !== null) return lead + whole + trail;
    var parts = core.split(/(\s*\u00b7\s*)/);
    if (parts.length > 1) {
      return lead + parts.map(function (p, i) {
        if (i % 2) return p;
        var t = p.trim(); if (!t) return p;
        var r = piece(t); if (r === null) r = bareDate(t);
        return r === null ? p : r;
      }).join("") + trail;
    }
    var d = bareDate(core);
    return d === null ? text : lead + d + trail;
  }

  // ---- applying it to the page
  var ATTRS = ["title", "aria-label", "placeholder", "alt"];
  var shown = new WeakMap();   // text node -> {orig, out}
  var attrOrig = new WeakMap(); // element -> {attr: {orig, out}}
  var SKIP = /^(SCRIPT|STYLE|NOSCRIPT)$/;

  function doText(node) {
    var rec = shown.get(node);
    var cur = node.nodeValue;
    if (rec && cur === rec.out) { /* we wrote this */ } else { rec = { orig: cur, out: cur }; }
    var out = lang === "es" ? translate(rec.orig) : rec.orig;
    if (out !== cur) node.nodeValue = out;
    rec.out = out;
    shown.set(node, rec);
  }
  function doAttrs(el) {
    var rec = attrOrig.get(el) || {};
    ATTRS.forEach(function (a) {
      if (!el.hasAttribute(a)) return;
      var cur = el.getAttribute(a), r = rec[a];
      if (!(r && cur === r.out)) r = { orig: cur, out: cur };
      var out = lang === "es" ? translate(r.orig) : r.orig;
      if (out !== cur) el.setAttribute(a, out);
      r.out = out; rec[a] = r;
    });
    attrOrig.set(el, rec);
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { if (!SKIP.test(root.parentNode && root.parentNode.nodeName || "")) doText(root); return; }
    if (root.nodeType !== 1 || SKIP.test(root.nodeName)) return;
    if (root.hasAttribute && ATTRS.some(function (a) { return root.hasAttribute(a); })) doAttrs(root);
    var w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) { return n.nodeType === 1 && SKIP.test(n.nodeName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT; }
    });
    var n;
    while ((n = w.nextNode())) { if (n.nodeType === 3) doText(n); else if (ATTRS.some(function (a) { return n.hasAttribute(a); })) doAttrs(n); }
  }

  var pending = false, queue = [];
  var observer = new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      if (m.type === "attributes") { queue.push(m.target); return; }
      m.addedNodes.forEach(function (n) { queue.push(n); });
    });
    if (pending) return;
    pending = true;
    (window.requestAnimationFrame || setTimeout)(function () {
      pending = false;
      var q = queue; queue = [];
      q.forEach(function (n) { if (n.isConnected) walk(n); });
    });
  });

  var TITLE_EN = document.title;
  var NOTE_ES = "Las descripciones de las citaciones y los resúmenes de daños aparecen en inglés por ahora. El resto de la página está en español.";

  function setLang(next, persist) {
    lang = next;
    if (persist) { try { localStorage.setItem(KEY, lang); } catch (e) {} }
    document.documentElement.setAttribute("lang", lang);
    titleOut = lang === "es" ? translate(TITLE_EN) : TITLE_EN;
    document.title = titleOut;
    walk(document.body);
    var btn = document.getElementById("langToggle");
    if (btn) {
      btn.textContent = lang === "es" ? "English" : "Español";
      btn.setAttribute("lang", lang === "es" ? "en" : "es");
      btn.setAttribute("aria-label", lang === "es" ? "Switch to English" : "Cambiar a español");
    }
    var note = document.getElementById("langNote");
    if (note) { note.hidden = lang !== "es"; note.textContent = lang === "es" ? NOTE_ES : ""; }
  }

  // the page script rewrites the tab title on every route change
  var titleEl = document.querySelector("title"), titleOut = null;
  function syncTitle() {
    if (!titleEl) return;
    var cur = document.title;
    if (cur === titleOut) return;
    TITLE_EN = cur;
    titleOut = lang === "es" ? translate(cur) : cur;
    if (titleOut !== cur) document.title = titleOut;
  }
  if (titleEl) new MutationObserver(syncTitle).observe(titleEl, { childList: true, characterData: true, subtree: true });

  function init() {
    var btn = document.getElementById("langToggle");
    if (btn) btn.addEventListener("click", function () { setLang(lang === "es" ? "en" : "es", true); });
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ATTRS });
    setLang(lang, false);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();

  window.RINH_I18N = { get lang() { return lang; }, set: function (l) { setLang(l, true); }, translate: translate, rules: pats.length + Object.keys(exact).length };
})();
