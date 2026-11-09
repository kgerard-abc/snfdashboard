/* Small QR code maker for ABC-RI's printable sheets. Written for these sites (November 2026),
   following the QR code standard (ISO/IEC 18004): byte mode, error correction level M,
   versions 1 to 6, which holds web addresses up to 106 characters. Nothing is sent anywhere;
   the code is drawn in the browser as an SVG image.
   Use: window.abcQR.svg("https://snfdashboard.abc-ri.org/#f-415002", 2.2)  -> "<svg ...>"  (size in cm)
   Checked by reading the codes back with OpenCV's QR reader for addresses of every length 1 to 106. */
(function () {
  "use strict";
  // Level M: [total codewords, error correction codewords per block, number of blocks] for versions 1 to 6
  var TABLE = [null, [26, 10, 1], [44, 16, 1], [70, 26, 1], [100, 18, 2], [134, 24, 2], [172, 16, 4]];
  var ALIGN = [null, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34]];

  function gfMul(x, y) {   // multiply in GF(2^8) modulo x^8 + x^4 + x^3 + x^2 + 1
    var z = 0;
    for (var i = 7; i >= 0; i--) {
      z = (z << 1) ^ ((z >>> 7) * 0x11D);
      z ^= ((y >>> i) & 1) * x;
    }
    return z & 0xFF;
  }
  function rsDivisor(degree) {
    var r = [];
    for (var i = 0; i < degree - 1; i++) r.push(0);
    r.push(1);
    var root = 1;
    for (i = 0; i < degree; i++) {
      for (var j = 0; j < r.length; j++) {
        r[j] = gfMul(r[j], root);
        if (j + 1 < r.length) r[j] ^= r[j + 1];
      }
      root = gfMul(root, 0x02);
    }
    return r;
  }
  function rsRemainder(data, div) {
    var r = div.map(function () { return 0; });
    data.forEach(function (b) {
      var f = b ^ r.shift();
      r.push(0);
      for (var i = 0; i < div.length; i++) r[i] ^= gfMul(div[i], f);
    });
    return r;
  }
  function utf8(s) {
    var out = [], e = unescape(encodeURIComponent(s));
    for (var i = 0; i < e.length; i++) out.push(e.charCodeAt(i));
    return out;
  }

  function make(text) {
    var bytes = utf8(text), ver = 0;
    for (var v = 1; v <= 6; v++) {
      var t = TABLE[v], dataCw = t[0] - t[1] * t[2];
      if (4 + 8 + bytes.length * 8 <= dataCw * 8) { ver = v; break; }
    }
    if (!ver) throw new Error("Text too long for this QR maker: " + text.length + " characters");
    var tab = TABLE[ver], total = tab[0], eccLen = tab[1], nBlocks = tab[2], dataLen = total - eccLen * nBlocks;

    // data bits: mode 0100 (byte), 8-bit length, the bytes, terminator, then pad
    var bits = [];
    function put(val, n) { for (var i = n - 1; i >= 0; i--) bits.push((val >>> i) & 1); }
    put(4, 4); put(bytes.length, 8); bytes.forEach(function (b) { put(b, 8); });
    put(0, Math.min(4, dataLen * 8 - bits.length));
    put(0, (8 - bits.length % 8) % 8);
    for (var pad = 0xEC; bits.length < dataLen * 8; pad ^= 0xEC ^ 0x11) put(pad, 8);
    var data = [];
    for (var i = 0; i < bits.length; i += 8) {
      var b = 0; for (var k = 0; k < 8; k++) b = (b << 1) | bits[i + k]; data.push(b);
    }

    // split into equal blocks (true for every level M version 1 to 6), add error correction, interleave
    var blockData = dataLen / nBlocks, div = rsDivisor(eccLen), blocks = [], eccs = [];
    for (i = 0; i < nBlocks; i++) {
      var d = data.slice(i * blockData, (i + 1) * blockData);
      blocks.push(d); eccs.push(rsRemainder(d, div));
    }
    var cw = [];
    for (i = 0; i < blockData; i++) blocks.forEach(function (bl) { cw.push(bl[i]); });
    for (i = 0; i < eccLen; i++) eccs.forEach(function (e) { cw.push(e[i]); });

    var size = 17 + 4 * ver, mod = [], fn = [];
    for (var y = 0; y < size; y++) { mod.push([]); fn.push([]); for (var x = 0; x < size; x++) { mod[y].push(false); fn[y].push(false); } }
    function setF(x, y, dark) { mod[y][x] = dark; fn[y][x] = true; }

    for (i = 0; i < size; i++) { setF(6, i, i % 2 === 0); setF(i, 6, i % 2 === 0); }      // timing patterns
    [[3, 3], [size - 4, 3], [3, size - 4]].forEach(function (c) {                          // finder patterns
      for (var dy = -4; dy <= 4; dy++) for (var dx = -4; dx <= 4; dx++) {
        var xx = c[0] + dx, yy = c[1] + dy, dist = Math.max(Math.abs(dx), Math.abs(dy));
        if (xx >= 0 && xx < size && yy >= 0 && yy < size) setF(xx, yy, dist !== 2 && dist !== 4);
      }
    });
    var al = ALIGN[ver];                                                                     // alignment pattern
    for (i = 0; i < al.length; i++) for (var j = 0; j < al.length; j++) {
      if ((i === 0 && j === 0) || (i === 0 && j === al.length - 1) || (i === al.length - 1 && j === 0)) continue;
      for (var ay = -2; ay <= 2; ay++) for (var ax = -2; ax <= 2; ax++)
        setF(al[i] + ax, al[j] + ay, Math.max(Math.abs(ax), Math.abs(ay)) !== 1);
    }
    function formatBits(mask) {
      var dat = (0 << 3) | mask, rem = dat;     // level M is 00
      for (var n = 0; n < 10; n++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
      var fb = ((dat << 10) | rem) ^ 0x5412, g = function (n) { return ((fb >>> n) & 1) !== 0; };
      for (n = 0; n <= 5; n++) setF(8, n, g(n));
      setF(8, 7, g(6)); setF(8, 8, g(7)); setF(7, 8, g(8));
      for (n = 9; n < 15; n++) setF(14 - n, 8, g(n));
      for (n = 0; n < 8; n++) setF(size - 1 - n, 8, g(n));
      for (n = 8; n < 15; n++) setF(8, size - 15 + n, g(n));
      setF(8, size - 8, true);                  // the dark module
    }
    formatBits(0);                               // reserve the format areas

    var bit = 0, nbits = cw.length * 8;          // place the codewords in the zigzag order
    for (var right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (var vert = 0; vert < size; vert++) for (j = 0; j < 2; j++) {
        x = right - j;
        var up = ((right + 1) & 2) === 0;
        y = up ? size - 1 - vert : vert;
        if (!fn[y][x] && bit < nbits) { mod[y][x] = ((cw[bit >>> 3] >>> (7 - (bit & 7))) & 1) !== 0; bit++; }
      }
    }

    var MASKS = [
      function (x, y) { return (x + y) % 2 === 0; }, function (x, y) { return y % 2 === 0; },
      function (x) { return x % 3 === 0; }, function (x, y) { return (x + y) % 3 === 0; },
      function (x, y) { return (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0; },
      function (x, y) { return x * y % 2 + x * y % 3 === 0; },
      function (x, y) { return (x * y % 2 + x * y % 3) % 2 === 0; },
      function (x, y) { return ((x + y) % 2 + x * y % 3) % 2 === 0; }];
    function applyMask(m) {
      for (var y = 0; y < size; y++) for (var x = 0; x < size; x++) if (!fn[y][x] && MASKS[m](x, y)) mod[y][x] = !mod[y][x];
    }
    function penalty() {   // the standard's four penalty rules, used to pick the easiest mask to read
      var p = 0, y, x, run, dark = 0, line, s;
      for (var pass = 0; pass < 2; pass++) for (y = 0; y < size; y++) {
        line = []; for (x = 0; x < size; x++) line.push(pass ? mod[x][y] : mod[y][x]);
        run = 1;
        for (x = 1; x <= size; x++) {
          if (x < size && line[x] === line[x - 1]) run++;
          else { if (run >= 5) p += 3 + run - 5; run = 1; }
        }
        s = line.map(function (v) { return v ? "1" : "0"; }).join("");
        var re = /(?=(10111010000|00001011101))/g, m;
        while ((m = re.exec(s))) { p += 40; re.lastIndex++; }
      }
      for (y = 0; y < size - 1; y++) for (x = 0; x < size - 1; x++) {
        var c = mod[y][x];
        if (c === mod[y][x + 1] && c === mod[y + 1][x] && c === mod[y + 1][x + 1]) p += 3;
      }
      for (y = 0; y < size; y++) for (x = 0; x < size; x++) if (mod[y][x]) dark++;
      p += Math.floor(Math.abs(dark * 20 - size * size * 10) / (size * size)) * 10;
      return p;
    }
    var best = 0, bestP = Infinity;
    for (var m = 0; m < 8; m++) {
      applyMask(m); formatBits(m);
      var pp = penalty();
      if (pp < bestP) { bestP = pp; best = m; }
      applyMask(m);                              // undo
    }
    applyMask(best); formatBits(best);
    return mod;
  }

  // SVG with a 4-module quiet zone, black on white; sizeCm is the printed width
  function svg(text, sizeCm) {
    var mod = make(text), n = mod.length, q = 4, w = n + 2 * q, d = "";
    for (var y = 0; y < n; y++) for (var x = 0; x < n; x++) if (mod[y][x]) d += "M" + (x + q) + " " + (y + q) + "h1v1h-1z";
    var sz = sizeCm ? ' width="' + sizeCm + 'cm" height="' + sizeCm + 'cm"' : "";
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + w + " " + w + '"' + sz +
      ' shape-rendering="crispEdges" role="img" aria-label="QR code"><rect width="' + w + '" height="' + w + '" fill="#fff"/><path d="' + d + '" fill="#000"/></svg>';
  }
  window.abcQR = { svg: svg, modules: make };
})();
