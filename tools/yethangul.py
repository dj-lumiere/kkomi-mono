"""Old Hangul: the archaic conjoining jamo, and a form of every conjoining jamo for each
place it can take in a syllable.

Old Hangul has no precomposed syllables. It is written as a run of conjoining jamo, an
initial, a vowel and maybe a final (ᄒ ᆞ ᆫ), and the font draws them one over another
in one syllable's two cells.

The jamo (U+1100..11FF, U+A960..A97C, U+D7B0..D7FB) are built from the font's own
compatibility jamo (ㄱ ㅏ ㆍ ㅿ ㆁ ㆆ ㅸ ㅺ ...), read off the Unicode name: a cluster with
a compatibility jamo of its own uses it whole, any other is put together from its
letters side by side (ᄓ is ㄴ and ㄱ). A vowel is split into its flat letters (ㅗ ㅛ ㅜ
ㅠ ㅡ ㆍ) and its upright letters (ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅣ): the flat ones go under the
initial, the upright ones to its right. A chitueum or ceongchieum sios, cieuc or chieuch
(ᄼ ᄾ) is drawn as the plain letter.

Each jamo has a default form, set in its fixed place in the two cells (the JAMO_SLOT
boxes the modern jamo use), for terminals and anything else that does not shape text.
Where text is shaped, ccmp picks a form for the place the jamo has in its syllable:
  an initial, by the class of the vowel after it and whether a final follows (6 forms),
  a vowel, by whether a final follows (2 forms),
  a final, by the class of the vowel before it (3 forms).
The places are learned from the syllables the designer drew (hangul_fill.learn_boxes),
so an old syllable puts its initial, vowel and final where a modern one would.
"""
import unicodedata

import make_mono as M

RANGES = list(range(0x1100, 0x1200)) + list(range(0xA960, 0xA97D)) + list(range(0xD7B0, 0xD7FC))
FLAT = {"O", "YO", "U", "YU", "EU", "ARAEA"}
TALL = {"A", "AE", "YA", "YAE", "EO", "E", "YEO", "YE", "I"}
# vowels with a name of their own, as the letters they are made of
VOWEL_PARTS = {"WA": ["O", "A"], "WAE": ["O", "AE"], "OE": ["O", "I"], "WEO": ["U", "EO"],
               "WE": ["U", "E"], "WI": ["U", "I"], "YI": ["EU", "I"], "ARAEAE": ["ARAEA", "I"]}
ROLE = {"CHOSEONG": "L", "JUNGSEONG": "V", "JONGSEONG": "T"}


def compat_letters(cmap):
    """{letter name: compatibility jamo code point} for the ones the font has."""
    out = {}
    for cp in range(0x3131, 0x318F):
        name = unicodedata.name(chr(cp), "")
        if name.startswith("HANGUL LETTER ") and cp in cmap:
            out[name[len("HANGUL LETTER "):]] = cp
    return out


def parse(cp):
    """(role, letter name) of a conjoining jamo, or None for the fillers and gaps."""
    name = unicodedata.name(chr(cp), "")
    parts = name.split(" ", 2)
    if len(parts) < 3 or parts[0] != "HANGUL" or parts[1] not in ROLE or "FILLER" in name:
        return None
    return ROLE[parts[1]], parts[2]


def consonant_atoms(key, letters):
    """The pieces a consonant is drawn from, left to right. A piece is a letter name, or
    ("kap", name) for a letter with a small ㅇ under it (the kapyeoun ones with no
    compatibility jamo)."""
    if key in letters:
        return [key]
    atoms = []
    for part in key.split("-"):
        if part in letters:
            atoms.append(part)
        elif part.startswith("SSANG") and part[5:] in letters:
            atoms += [part[5:], part[5:]]
        elif part.startswith("KAPYEOUN") and part[8:] in letters:
            atoms.append(("kap", part[8:]))
        elif part.startswith("CHITUEUM") and part[8:] in letters:
            atoms.append(part[8:])
        elif part.startswith("CEONGCHIEUM") and part[11:] in letters:
            atoms.append(part[11:])
        elif part.startswith("SSANG") and part[5:].startswith("CHITUEUM"):
            atoms += [part[13:], part[13:]]
        elif part.startswith("SSANG") and part[5:].startswith("CEONGCHIEUM"):
            atoms += [part[16:], part[16:]]
        else:
            raise SystemExit(f"old Hangul: no letter for {part} in {key}")
    return atoms


def vowel_atoms(key):
    """The basic vowel letters a vowel is made of, in order."""
    out = []
    for part in key.split("-"):
        if part in VOWEL_PARTS:
            out += VOWEL_PARTS[part]
        elif part.startswith("SSANG"):
            out += [part[5:], part[5:]]
        elif part in FLAT or part in TALL:
            out.append(part)
        else:
            raise SystemExit(f"old Hangul: no vowel letter for {part} in {key}")
    return out


def vowel_class(atoms):
    """0: upright letters only (to the right), 1: flat only (below), 2: both."""
    flat = any(a in FLAT for a in atoms)
    tall = any(a in TALL for a in atoms)
    return 2 if flat and tall else 1 if flat else 0


def add(font, to_glyph, weight, boxes, slots, stroke):
    """Adds the archaic jamo and the place forms of every conjoining jamo. boxes: the
    learned places (hangul_fill.learn_boxes). slots: the fixed places of the default
    forms, {"initial", "tall", "flat", "final": box}. stroke: the width of a stroke the
    jamo are given back to after scaling. Returns (new glyph names, the base glyphs of
    each role {"L", "V", "T": [names]}, feature code for ccmp)."""
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()
    glyf, hmtx = font["glyf"], font["hmtx"]
    wide = 2 * M.CELL
    letters = compat_letters(cmap)
    need = [("initial", c, f) for c in range(3) for f in (False, True)] + \
           [("tall", c, f) for c in (0, 2) for f in (False, True)] + \
           [("flat", c, f) for c in (1, 2) for f in (False, True)] + [("final", c) for c in range(3)]
    missing = [k for k in need if k not in boxes]
    if missing:
        raise SystemExit(f"old Hangul: too few drawn syllables to learn {missing}")

    def shape(atom):
        if isinstance(atom, tuple):
            # a letter with a small ㅇ under it
            top = M.record(gs, cmap[letters[atom[1]]])
            ring = M.record(gs, cmap[letters["IEUNG"]])
            tb, rb = M.bounds(top), M.bounds(ring)
            k = 0.45
            ring = M.transformed(ring, k, (tb[0] + tb[2]) / 2 - k * (rb[0] + rb[2]) / 2,
                                 k, tb[1] - 30 - k * rb[3])
            return top + weight(ring, stroke * (1 - k), stroke * (1 - k))
        return M.record(gs, cmap[letters[atom]])

    ref_h = M.bounds(shape("KIYEOK"))[3] - M.bounds(shape("KIYEOK"))[1]

    def row(atoms, gap=0.14):
        """Pieces side by side at the height of ㄱ, a little apart."""
        out, x = [], 0.0
        for a in atoms:
            ops = shape(a)
            b = M.bounds(ops)
            k = ref_h / (b[3] - b[1]) if len(atoms) > 1 else 1.0
            k = min(k, 1.0)
            ops = M.transformed(ops, k, x - k * b[0], k, -k * b[1])
            if k < 0.98:
                ops = weight(ops, stroke * (1 - k), stroke * (1 - k))
            out += ops
            x = M.bounds(out)[2] + gap * ref_h
        return out

    def stack(atoms, gap=0.12):
        """Flat vowel letters one under the other, in order from the top."""
        out, y = [], 0.0
        for a in atoms:
            ops = shape(a)
            b = M.bounds(ops)
            ops = M.transformed(ops, 1.0, -(b[0] + b[2]) / 2, 1.0, y - b[3])
            out += ops
            y = M.bounds(out)[1] - gap * ref_h
        return out

    def place(ops, box, ref):
        """ops scaled as ref would be to fit box (so a dot stays a dot), then narrowed
        or lowered further if it still does not fit, stroke given back, and centred."""
        rb, b = M.bounds(ref), M.bounds(ops)
        bw, bh = box[2] - box[0], box[3] - box[1]
        k = min(bw / (rb[2] - rb[0]), bh / (rb[3] - rb[1]))
        kx = min(k, bw / (b[2] - b[0]))
        ky = min(k, bh / (b[3] - b[1]))
        # a cluster may narrow to half the height's scale before it shrinks as a whole
        if kx < ky * 0.5:
            ky = kx * 2
        out = M.transformed(ops, kx, 0.0, ky, 0.0)
        out = weight(out, stroke * (1 - kx), stroke * (1 - ky))
        ob = M.bounds(out)
        return M.transformed(out, 1.0, (box[0] + box[2]) / 2 - (ob[0] + ob[2]) / 2,
                             1.0, (box[1] + box[3]) / 2 - (ob[1] + ob[3]) / 2)

    ref_consonant = shape("KIYEOK")
    ref_tall, ref_flat = shape("A"), shape("O")

    def consonant(atoms, box):
        return place(row(atoms), box, ref_consonant)

    def vowel(atoms, tall_box, flat_box):
        talls = [a for a in atoms if a in TALL]
        flats = [a for a in atoms if a in FLAT]
        out = []
        if flats:
            out += place(stack(flats), flat_box, ref_flat)
        if talls:
            out += place(row(talls, gap=0.05), tall_box, ref_tall)
        return out

    jamo = {}                       # cp -> (role, atoms, vowel class or None)
    for cp in RANGES:
        p = parse(cp)
        if p is None:
            continue
        role, key = p
        if role == "V":
            atoms = vowel_atoms(key)
            jamo[cp] = (role, atoms, vowel_class(atoms))
        else:
            jamo[cp] = (role, consonant_atoms(key, letters), None)

    new, base = [], {"L": [], "V": [], "T": []}
    order = font.getGlyphOrder()

    def put(name, ops, adv, dx):
        glyf[name] = to_glyph(M.transformed(ops, 1.0, dx) if dx else ops)
        hmtx[name] = (adv, 0)
        new.append(name)

    for cp, (role, atoms, cls) in jamo.items():
        name = cmap.get(cp) or f"uni{cp:04X}"
        if cp not in cmap:
            # the default form, in the fixed places
            if role == "L":
                put(name, consonant(atoms, slots["initial"]), wide, 0)
            elif role == "V":
                put(name, vowel(atoms, slots["tall"], slots["flat"]), 0, -wide)
            else:
                put(name, consonant(atoms, slots["final"]), 0, -wide)
            for table in font["cmap"].tables:
                if table.isUnicode():
                    table.cmap[cp] = name
        base[role].append(name)
        if role == "L":
            for c in range(3):
                for f in (False, True):
                    put(f"{name}.L{c}{int(f)}", consonant(atoms, boxes[("initial", c, f)]), wide, 0)
        elif role == "V":
            for f in (False, True):
                put(f"{name}.V{int(f)}", vowel(atoms, boxes.get(("tall", cls, f)), boxes.get(("flat", cls, f))),
                    0, -wide)
        else:
            for c in range(3):
                put(f"{name}.T{c}", consonant(atoms, boxes[("final", c)]), 0, -wide)
    font.setGlyphOrder(order + [n for n in new if n not in order])
    glyf.glyphOrder = font.getGlyphOrder()

    cls_of = {}
    for cp, (role, atoms, cls) in jamo.items():
        if role == "V":
            cls_of[font.getBestCmap()[cp]] = cls
    L, V, T = base["L"], base["V"], base["T"]
    Vc = [[v for v in V if cls_of[v] == c] for c in range(3)]

    def cls_line(name, glyphs):
        return f"@{name} = [{' '.join(glyphs)}];\n"

    fea = cls_line("OH_L", L) + cls_line("OH_V", V) + cls_line("OH_T", T)
    for c in range(3):
        fea += cls_line(f"OH_V{c}", Vc[c])
        fea += cls_line(f"OH_T_{c}", [f"{t}.T{c}" for t in T])
        for f in (0, 1):
            fea += cls_line(f"OH_L_{c}{f}", [f"{x}.L{c}{f}" for x in L])
    fea += cls_line("OH_L_ANY", L + [f"{x}.L{c}{f}" for x in L for c in range(3) for f in (0, 1)])
    for f in (0, 1):
        fea += cls_line(f"OH_V_{f}", [f"{v}.V{f}" for v in V])
    for c in range(3):
        for f in (0, 1):
            fea += f"lookup oh_l_{c}{f} {{\n    sub @OH_L by @OH_L_{c}{f};\n}} oh_l_{c}{f};\n"
        fea += f"lookup oh_t_{c} {{\n    sub @OH_T by @OH_T_{c};\n}} oh_t_{c};\n"
    for f in (0, 1):
        fea += f"lookup oh_v_{f} {{\n    sub @OH_V by @OH_V_{f};\n}} oh_v_{f};\n"
    # initials first, while the vowels and finals after them are still in their base form
    fea += "lookup oh_initial {\n"
    for c in range(3):
        fea += f"    sub @OH_L' lookup oh_l_{c}1 @OH_V{c} @OH_T;\n"
    for c in range(3):
        fea += f"    sub @OH_L' lookup oh_l_{c}0 @OH_V{c};\n"
    fea += "} oh_initial;\n"
    fea += "lookup oh_final {\n"
    for c in range(3):
        fea += f"    sub @OH_V{c} @OH_T' lookup oh_t_{c};\n"
    fea += "} oh_final;\n"
    fea += "lookup oh_vowel {\n" \
           "    sub @OH_L_ANY @OH_V' lookup oh_v_1 @OH_T;\n" \
           "    sub @OH_L_ANY @OH_V' lookup oh_v_0;\n" \
           "} oh_vowel;\n"
    return new, base, fea
