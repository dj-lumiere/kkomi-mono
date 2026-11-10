"""Writes chars.html: every character the font maps, grouped by Unicode block.

    python make_charmap.py ../fonts/KNPSKkomiMono-Regular.ttf ../chars.html

The page loads the font from fonts/woff2/, so it works next to index.html.
"""
import html
import json
import sys
import unicodedata

from fontTools.ttLib import TTFont

# (first, last, Korean label, Unicode block name)
BLOCKS = [
    (0x0000, 0x007F, "기본 라틴", "Basic Latin"),
    (0x0080, 0x00FF, "라틴-1 보충", "Latin-1 Supplement"),
    (0x0100, 0x017F, "라틴 확장-A", "Latin Extended-A"),
    (0x02B0, 0x02FF, "간격 수정 문자", "Spacing Modifier Letters"),
    (0x0370, 0x03FF, "그리스 문자", "Greek and Coptic"),
    (0x0400, 0x04FF, "키릴 문자", "Cyrillic"),
    (0x1100, 0x11FF, "한글 자모 (조합용)", "Hangul Jamo"),
    (0x2000, 0x206F, "일반 문장 부호", "General Punctuation"),
    (0x2070, 0x209F, "위·아래 첨자", "Superscripts and Subscripts"),
    (0x20A0, 0x20CF, "통화 기호", "Currency Symbols"),
    (0x2100, 0x214F, "글자 모양 기호", "Letterlike Symbols"),
    (0x2150, 0x218F, "숫자 꼴 (분수, 로마 숫자)", "Number Forms"),
    (0x2190, 0x21FF, "화살표", "Arrows"),
    (0x2200, 0x22FF, "수학 연산자", "Mathematical Operators"),
    (0x2300, 0x23FF, "기타 기술 기호", "Miscellaneous Technical"),
    (0x2400, 0x243F, "제어 문자 그림", "Control Pictures"),
    (0x2460, 0x24FF, "둘러싼 영숫자", "Enclosed Alphanumerics"),
    (0x2500, 0x257F, "박스 선", "Box Drawing"),
    (0x2580, 0x259F, "블록", "Block Elements"),
    (0x25A0, 0x25FF, "도형", "Geometric Shapes"),
    (0x2600, 0x26FF, "기타 기호", "Miscellaneous Symbols"),
    (0x2700, 0x27BF, "딩뱃", "Dingbats"),
    (0x27C0, 0x27EF, "기타 수학 기호-A", "Miscellaneous Mathematical Symbols-A"),
    (0x2800, 0x28FF, "점자", "Braille Patterns"),
    (0x3000, 0x303F, "한중일 기호와 문장 부호", "CJK Symbols and Punctuation"),
    (0x3040, 0x309F, "히라가나", "Hiragana"),
    (0x30A0, 0x30FF, "가타카나", "Katakana"),
    (0x3130, 0x318F, "한글 호환 자모", "Hangul Compatibility Jamo"),
    (0x3200, 0x32FF, "둘러싼 한글과 한자", "Enclosed CJK Letters and Months"),
    (0x3300, 0x33FF, "한중일 호환 (단위)", "CJK Compatibility"),
    (0xAC00, 0xD7AF, "한글 음절", "Hangul Syllables"),
    (0xE000, 0xF8FF, "사용자 정의 영역 (Powerline)", "Private Use Area"),
    (0xFF00, 0xFFEF, "전각·반각 문자", "Halfwidth and Fullwidth Forms"),
    (0xFFF0, 0xFFFF, "특수 문자", "Specials"),
]

# The ligatures the font forms by default, read from the build so the list cannot
# drift from the font (the opt-in ones of a stylistic set are left out).
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import make_mono as M  # noqa: E402
LIGATURES = [chars for name, chars in M.LIGATURES if name not in M.STYLISTIC]

POWERLINE = {0xE0A0: "Powerline branch", 0xE0A1: "Powerline line number", 0xE0A2: "Powerline lock",
             0xE0B0: "Powerline right arrow", 0xE0B1: "Powerline right thin arrow",
             0xE0B2: "Powerline left arrow", 0xE0B3: "Powerline left thin arrow"}


def char_name(cp):
    return POWERLINE.get(cp) or unicodedata.name(chr(cp), "")


def main():
    font_path, out_path = sys.argv[1:3]
    cmap = TTFont(font_path).getBestCmap()
    cps = sorted(cp for cp in cmap if cp > 0x20 and unicodedata.category(chr(cp)) != "Cc")

    blocks, hangul = [], []
    for first, last, ko, en in BLOCKS:
        inside = [cp for cp in cps if first <= cp <= last]
        if not inside:
            continue
        if en == "Hangul Syllables":
            hangul = inside
            continue
        blocks.append({"ko": ko, "en": en,
                       "c": [[cp, char_name(cp), unicodedata.east_asian_width(chr(cp)) in "WF"] for cp in inside]})
    listed = {cp for b in blocks for cp, _, _ in b["c"]} | set(hangul)
    rest = [cp for cp in cps if cp not in listed]
    if rest:
        blocks.append({"ko": "그 밖", "en": "Other",
                       "c": [[cp, char_name(cp), unicodedata.east_asian_width(chr(cp)) in "WF"] for cp in rest]})

    total = len(cps)
    data = json.dumps(blocks, ensure_ascii=False, separators=(",", ":"))
    ligs = "".join(f'<span class="lg"><b>{html.escape(s)}</b><i>{html.escape(s)}</i></span>' for s in LIGATURES)
    toc = "".join(f'<a href="#b{i}">{html.escape(b["ko"])}</a>' for i, b in enumerate(blocks))
    toc += '<a href="#hangul">한글 음절</a><a href="#ligatures">리거처</a>'

    page = TEMPLATE.replace("{{TOTAL}}", f"{total:,}").replace("{{TOC}}", toc) \
        .replace("{{HANGUL_COUNT}}", f"{len(hangul):,}") \
        .replace("{{LIGS}}", ligs).replace("{{DATA}}", data)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"wrote {out_path}: {total} characters, {len(blocks)} blocks")


TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>KNPS Kkomi Mono 글자 목록</title>
<meta name="description" content="KNPS Kkomi Mono가 지원하는 모든 글자">
<style>
/* Layout: a block index, then one grid of character cells per Unicode block. */
@font-face { font-family: "KKM"; src: url("fonts/woff2/KNPSKkomiMono-Regular.woff2") format("woff2"); font-style: normal; font-display: swap; }
@font-face { font-family: "KKM"; src: url("fonts/woff2/KNPSKkomiMono-Italic.woff2") format("woff2"); font-style: italic; font-display: swap; }
@font-face { font-family: "KKM"; src: url("fonts/woff2/KNPSKkomiMono-Bold.woff2") format("woff2"); font-weight: 700; font-display: swap; }
@font-face { font-family: "KKM"; src: url("fonts/woff2/KNPSKkomiMono-BoldItalic.woff2") format("woff2"); font-weight: 700; font-style: italic; font-display: swap; }
:root {
  /* one dark purple look, the same in light and dark system themes */
  --bg: #17111f; --panel: #1f1729; --fg: #ece4f5; --muted: #a196b3; --line: #352a45;
  --accent: #c39bf5; --grid: rgba(195,155,245,0.18);
  --mono: "KKM", ui-monospace, monospace;
  color-scheme: dark;
}
body { margin: 0; background: var(--bg); color: var(--fg); font-family: var(--mono); }
.wrap { max-width: 1100px; margin: 0 auto; padding-block: 28px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 26px; }
header h1 { margin: 0; font-size: 36px; font-weight: 400; }
header p { margin: 6px 0 0; color: var(--muted); font-size: 14px; line-height: 1.6; }
a { color: var(--accent); }
.bar { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; font-size: 14px;
  position: sticky; top: env(safe-area-inset-top, 0px); background: var(--bg); padding-block: 8px; z-index: 2; }
.group { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.group label { color: var(--muted); margin-right: 4px; }
button.t { font: inherit; font-size: 14px; padding: 5px 10px; border: 1px solid var(--line); background: var(--panel);
  color: var(--fg); border-radius: 4px; cursor: pointer; }
button.t[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); }
button.t:focus-visible, input:focus-visible, .c:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
input[type="range"] { accent-color: var(--accent); width: 120px; }
input[type="search"] { font: inherit; font-size: 14px; padding: 5px 8px; border: 1px solid var(--line);
  background: var(--panel); color: var(--fg); border-radius: 4px; width: 14em; }
nav.toc { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 13px; line-height: 1.5; }
section { display: grid; gap: 8px; min-width: 0; scroll-margin-top: 64px; }
h2 { margin: 0; font-size: 15px; font-weight: 400; display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; }
h2 small { color: var(--muted); font-size: 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(calc(var(--size, 32px) * 1.6 + 16px), 1fr));
  gap: 1px; background: var(--line); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.c { background: var(--panel); display: grid; justify-items: center; gap: 4px; padding: 10px 2px 6px;
  cursor: pointer; min-width: 0; font: inherit; color: inherit; border: 0; }
.c:hover { background: var(--bg); }
.g { font-size: var(--size, 32px); line-height: 1.25; white-space: pre; font-feature-settings: "calt" 0; }
.cell-on .g { background-image: linear-gradient(to right, var(--grid) 1px, transparent 1px);
  background-size: 0.5em 100%; box-shadow: inset -1px 0 var(--grid); }
.u { font-size: 10px; color: var(--muted); font-variant-numeric: tabular-nums; }
.it .g, .it .lg b { font-style: italic; }
.bd .g, .bd .lg b { font-weight: 700; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; overflow-x: auto; }
details.ini { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; }
details.ini + details.ini { margin-top: 6px; }
details.ini summary { padding: 10px 16px; }
.tbl { overflow-x: auto; }
table.hg { border-collapse: collapse; margin: 0 16px 14px; }
table.hg th { font-weight: 400; color: var(--muted); font-size: 13px; padding: 4px 6px; }
table.hg td { padding: 0; border: 1px solid var(--line); }
table.hg button { font: inherit; color: inherit; background: none; border: 0; cursor: pointer;
  font-size: calc(var(--size, 32px) * 0.8); line-height: 1.3; padding: 4px 6px; }
table.hg button:hover { background: var(--bg); }
table.hg button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.it table.hg button { font-style: italic; }
.bd table.hg button { font-weight: 700; }
summary { cursor: pointer; font-size: 15px; }
summary small { color: var(--muted); font-size: 12px; }
.ligs { display: flex; flex-wrap: wrap; gap: 6px 26px; padding: 14px 16px; }
.lg { display: grid; gap: 2px; justify-items: start; }
.lg b { font-weight: 400; font-size: var(--size, 32px); }
.lg i { font-style: normal; font-size: 12px; color: var(--muted); font-feature-settings: "calt" 0; }
#toast { position: fixed; bottom: calc(16px + env(safe-area-inset-bottom, 0px)); left: 50%; transform: translateX(-50%);
  background: var(--fg); color: var(--bg); padding: 6px 12px; border-radius: 4px; font-size: 13px; }
footer { color: var(--muted); font-size: 13px; line-height: 1.6; }
@media (prefers-reduced-motion: no-preference) { .c { transition: background .1s; } }
</style>
</head>
<body>
<div class="wrap" id="root">
  <header>
    <h1>글자 목록</h1>
    <p>KNPS Kkomi Mono가 그리는 글자 {{TOTAL}}자입니다. 칸을 누르면 글자가 복사됩니다.</p>
    <p><a href="./">미리보기로 돌아가기</a> · <a href="https://github.com/dj-lumiere/kkomi-mono/releases/latest">내려받기</a></p>
  </header>

  <div class="bar">
    <div class="group" role="group" aria-label="굵기와 기울기">
      <label>벌</label>
      <button class="t" id="st-r" aria-pressed="true" data-st="">Regular</button>
      <button class="t" id="st-i" aria-pressed="false" data-st="it">Italic</button>
      <button class="t" id="st-b" aria-pressed="false" data-st="bd">Bold</button>
      <button class="t" id="st-bi" aria-pressed="false" data-st="bd it">Bold Italic</button>
    </div>
    <div class="group">
      <label for="size">크기</label>
      <input id="size" type="range" min="16" max="64" value="32">
    </div>
    <div class="group">
      <button class="t" id="cells" aria-pressed="false">칸 경계</button>
    </div>
    <div class="group">
      <label for="q">찾기</label>
      <input id="q" type="search" placeholder="글자, U+00B7, arrow">
    </div>
  </div>

  <nav class="toc" aria-label="블록">{{TOC}}</nav>

  <div id="blocks"></div>

  <section id="hangul">
    <h2>한글 음절 <small>Hangul Syllables · {{HANGUL_COUNT}}자 · 초성마다 표 하나, 세로는 중성, 가로는 종성</small></h2>
    <div id="hangul-tables"></div>
  </section>

  <section id="ligatures">
    <h2>리거처 <small>calt · 아래 작은 글씨가 입력한 글자</small></h2>
    <div class="panel ligs">{{LIGS}}</div>
  </section>

  <footer>본 저작물은 국립공원공단에서 2021년 작성하여 공공누리 제1유형으로 개방한 국립공원공단 꼬미(작성자: 국립공원공단)를 이용하였으며, 해당 저작물은 국립공원공단, http://www.knps.or.kr 에서 무료로 다운받으실 수 있습니다.</footer>
</div>
<div id="toast" hidden></div>
<script>
const BLOCKS = {{DATA}};
const root = document.getElementById("root");
const host = document.getElementById("blocks");
const hex = cp => "U+" + cp.toString(16).toUpperCase().padStart(4, "0");
const frag = document.createDocumentFragment();
BLOCKS.forEach((b, i) => {
  const s = document.createElement("section");
  s.id = "b" + i;
  s.innerHTML = `<h2>${b.ko} <small>${b.en} · ${b.c.length}자</small></h2>`;
  const g = document.createElement("div");
  g.className = "grid";
  for (const [cp, name, wide] of b.c) {
    const c = document.createElement("button");
    c.className = "c";
    c.type = "button";
    c.title = `${hex(cp)} ${name}${wide ? " (두 칸)" : ""}`;
    c.dataset.k = `${String.fromCodePoint(cp)} ${hex(cp)} ${name}`.toLowerCase();
    c.innerHTML = `<span class="g"></span><span class="u">${hex(cp).slice(2)}</span>`;
    // a medial or final jamo has no width of its own: it is shown after the initial
    // filler (U+115F), in the two cells it belongs to
    const joins = cp >= 0x1160 && cp <= 0x11FF;
    c.firstChild.textContent = (joins ? "\u115F" : "") + String.fromCodePoint(cp);
    c.addEventListener("click", () => copy(String.fromCodePoint(cp), hex(cp)));
    g.appendChild(c);
  }
  s.appendChild(g);
  frag.appendChild(s);
});
host.appendChild(frag);

// 한글 음절: one table per initial, vowels down the side, finals across the top
const INITIALS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ";
const VOWELS = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ";
const FINALS = ["–", ..."ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"];
const tables = document.getElementById("hangul-tables");
function hangulTable(i) {
  const head = "<tr><th></th>" + FINALS.map(f => `<th>${f}</th>`).join("") + "</tr>";
  let rows = "";
  for (let v = 0; v < 21; v++) {
    rows += `<tr><th>${VOWELS[v]}</th>`;
    for (let f = 0; f < 28; f++) {
      const ch = String.fromCodePoint(0xAC00 + i * 588 + v * 28 + f);
      rows += `<td><button type="button">${ch}</button></td>`;
    }
    rows += "</tr>";
  }
  return `<div class="tbl"><table class="hg">${head}${rows}</table></div>`;
}
[...INITIALS].forEach((ini, i) => {
  const d = document.createElement("details");
  d.className = "ini";
  d.innerHTML = `<summary>${ini} <small>${String.fromCodePoint(0xAC00 + i * 588)} ~ ${String.fromCodePoint(0xAC00 + i * 588 + 587)} · 588자</small></summary>`;
  // the table is built the first time it is opened
  d.addEventListener("toggle", () => {
    if (d.open && !d.querySelector("table")) d.insertAdjacentHTML("beforeend", hangulTable(i));
  });
  if (i === 0) d.open = true;
  tables.appendChild(d);
});
tables.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (b) copy(b.textContent, "U+" + b.textContent.codePointAt(0).toString(16).toUpperCase());
});

const toast = document.getElementById("toast");
let timer;
function show(msg) {
  toast.textContent = msg; toast.hidden = false;
  clearTimeout(timer); timer = setTimeout(() => { toast.hidden = true; }, 1400);
}
function copy(ch, code) {
  const done = () => show(`${ch} ${code} 복사함`);
  if (navigator.clipboard) navigator.clipboard.writeText(ch).then(done, () => show(`${ch} ${code}`));
  else show(`${ch} ${code}`);
}

const styles = document.querySelectorAll("[data-st]");
styles.forEach(btn => btn.addEventListener("click", () => {
  root.classList.remove("it", "bd");
  btn.dataset.st.split(" ").filter(Boolean).forEach(c => root.classList.add(c));
  styles.forEach(o => o.setAttribute("aria-pressed", String(o === btn)));
}));
document.getElementById("size").addEventListener("input", e => {
  root.style.setProperty("--size", e.target.value + "px");
});
const cellsBtn = document.getElementById("cells");
cellsBtn.addEventListener("click", () => {
  const on = root.classList.toggle("cell-on");
  cellsBtn.setAttribute("aria-pressed", String(on));
});
document.getElementById("q").addEventListener("input", e => {
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll("#blocks section").forEach(s => {
    let any = false;
    s.querySelectorAll(".c").forEach(c => {
      const hit = !q || c.dataset.k.includes(q);
      c.hidden = !hit; any = any || hit;
    });
    s.hidden = !any;
  });
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
