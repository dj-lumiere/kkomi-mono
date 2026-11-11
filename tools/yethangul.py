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
        elif part.startswith("CHITUEUM") and part[8:].startswith("SSANG") and part[13:] in letters:
            atoms += [("chi", part[13:]), ("chi", part[13:])]
        elif part.startswith("CEONGCHIEUM") and part[11:].startswith("SSANG") and part[16:] in letters:
            atoms += [("ceong", part[16:]), ("ceong", part[16:])]
        elif part.startswith("CHITUEUM") and part[8:] in letters:
            atoms.append(("chi", part[8:]))
        elif part.startswith("CEONGCHIEUM") and part[11:] in letters:
            atoms.append(("ceong", part[11:]))
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


# the modern vowels, in jamo order, as letter names
MODERN_VOWELS = ["A", "AE", "YA", "YAE", "EO", "E", "YEO", "YE", "O", "WA", "WAE", "OE", "YO",
                 "U", "WEO", "WE", "WI", "YU", "EU", "YI", "I"]
# the modern vowel whose place an old one takes, by its first flat letter: on its own
# (ㆍ where ㅡ is), or with upright letters beside it (ᆡ where ㅢ is)
FLAT_TEMPLATE = {"O": 8, "YO": 12, "U": 13, "YU": 17, "EU": 18, "ARAEA": 18}
MIXED_TEMPLATE = {"O": 9, "YO": 9, "U": 14, "YU": 14, "EU": 19, "ARAEA": 19}
# upright letters with two stems
TWO_STEMS = {"AE", "YAE", "E", "YE"}
# flat letter, then one or two stems on the right: ㅚ ㅙ, ㅟ ㅞ, ㅢ
MIXED_BY_STEMS = {"O": {1: 11, 2: 10}, "U": {1: 16, 2: 15}, "EU": {1: 19, 2: 19}}


def vowel_template(atoms):
    """The modern vowel (index) whose place a vowel made of these letters takes."""
    flats = [a for a in atoms if a in FLAT]
    talls = [a for a in atoms if a in TALL]
    if atoms[0] in TALL:
        # an upright letter first (ᅶ ᆜ ᆙ): it stands where that letter would, any flat
        # letter after it goes small under it
        return MODERN_VOWELS.index(talls[0]) if len(talls) == 1 else MODERN_VOWELS.index("AE")
    for n, name in enumerate(MODERN_VOWELS):
        if vowel_atoms(name) == atoms:
            return n
    if flats and talls:
        # a flat letter, then upright letters: the modern vowel with the same flat
        # letter and as many stems on the right (ㅜㅕ as ㅟ, ㅜ with ㅣㅣ as ㅞ), the
        # upright letters put in the place of its right part
        stems = sum(2 if a in TWO_STEMS else 1 for a in talls)
        kind = {"O": "O", "YO": "O", "U": "U", "YU": "U", "EU": "EU", "ARAEA": "EU"}[flats[0]]
        return MIXED_BY_STEMS[kind][min(stems, 2)]
    if flats:
        return FLAT_TEMPLATE[flats[0]]
    if len(talls) == 1:
        return MODERN_VOWELS.index(talls[0])
    return MODERN_VOWELS.index("AE")


# the modern initials and finals, in jamo order, as letter names
MODERN_INITIALS = ["KIYEOK", "SSANGKIYEOK", "NIEUN", "TIKEUT", "SSANGTIKEUT", "RIEUL", "MIEUM",
                   "PIEUP", "SSANGPIEUP", "SIOS", "SSANGSIOS", "IEUNG", "CIEUC", "SSANGCIEUC",
                   "CHIEUCH", "KHIEUKH", "THIEUTH", "PHIEUPH", "HIEUH"]
MODERN_FINALS = [None, "KIYEOK", "SSANGKIYEOK", "KIYEOK-SIOS", "NIEUN", "NIEUN-CIEUC", "NIEUN-HIEUH",
                 "TIKEUT", "RIEUL", "RIEUL-KIYEOK", "RIEUL-MIEUM", "RIEUL-PIEUP", "RIEUL-SIOS",
                 "RIEUL-THIEUTH", "RIEUL-PHIEUPH", "RIEUL-HIEUH", "MIEUM", "PIEUP", "PIEUP-SIOS",
                 "SIOS", "SSANGSIOS", "IEUNG", "CIEUC", "CHIEUCH", "KHIEUKH", "THIEUTH", "PHIEUPH", "HIEUH"]
# old letters drawn at the size of a modern one
LETTER_TEMPLATE = {"PANSIOS": "SIOS", "YESIEUNG": "IEUNG", "YEORINHIEUH": "HIEUH",
                   "KAPYEOUNPIEUP": "PIEUP", "KAPYEOUNMIEUM": "MIEUM", "KAPYEOUNPHIEUPH": "PHIEUPH",
                   "KAPYEOUNSSANGPIEUP": "SSANGPIEUP", "SSANGNIEUN": "SSANGTIKEUT",
                   "SSANGIEUNG": "SSANGSIOS", "SSANGHIEUH": "SSANGSIOS"}


def letter_name(atom):
    return atom[1] if isinstance(atom, tuple) else atom


def consonant_template(atoms, role):
    """The modern initial or final (index) whose place and size a consonant made of
    these pieces takes: itself, the modern letter an old one is drawn like, or for a
    cluster a modern double (ㅃ for ᄢ, ㄺ for ᇘ)."""
    modern = MODERN_INITIALS if role == "L" else MODERN_FINALS
    if len(atoms) == 1:
        name = LETTER_TEMPLATE.get(letter_name(atoms[0]), letter_name(atoms[0]))
        if isinstance(atoms[0], tuple) and atoms[0][0] == "kap":
            name = LETTER_TEMPLATE.get("KAPYEOUN" + atoms[0][1], atoms[0][1])
        if name in modern:
            return modern.index(name)
    first = LETTER_TEMPLATE.get(letter_name(atoms[0]), letter_name(atoms[0]))
    if role == "L":
        double = {"KIYEOK": 1, "TIKEUT": 4, "PIEUP": 8, "SIOS": 10, "CIEUC": 13}
        return double.get(first, 10)
    if len(atoms) == 2 and f"{first}-{letter_name(atoms[1])}" in modern:
        return modern.index(f"{first}-{letter_name(atoms[1])}")
    double = {"KIYEOK": 3, "NIEUN": 5, "RIEUL": 9, "PIEUP": 18, "SIOS": 20}
    return double.get(first, 9)


def vowel_class(atoms):
    """0: upright letters only (to the right), or an upright letter first, 1: flat only
    (below), 2: flat letters first, then upright ones."""
    if atoms[0] in TALL:
        return 0
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
        if isinstance(atom, tuple) and atom[0] in ("chi", "ceong"):
            return one_leg_short(M.record(gs, cmap[letters[atom[1]]]), left=atom[0] == "ceong")
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

    def one_leg_short(ops, left):
        """ㅅ ㅈ ㅊ with one leg half as long: the right leg for the chitueum letters (ᄼ),
        the left leg for the ceongchieum letters (ᄾ), measured from its foot to where
        the two legs part. The letters are lopsided already, so only a leg cut this far
        shows. The leg's end keeps the pen's round shape: it is moved up the leg."""
        import pathops
        from make_italic import path_op, box
        flat = M.flattened(ops)
        b = M.bounds(flat)
        cx = (b[0] + b[2]) / 2
        # where the legs part: going up from the bottom, past the height where both
        # legs are crossed, the first height where they have joined into one stroke
        # (the bars of ㅈ ㅊ above do not count)
        part, seen, y = b[3], False, b[1] + 2
        while y < b[3]:
            n = len(M.crossings(flat, y))
            if n >= 4:
                seen = True
            elif seen:
                part = y
                break
            y += 5
        # the foot of the leg being cut, which may stop short of the letter's bottom
        pts = [q for poly in M.polygon_points(flat) for q in poly]
        foot = min((q[1] for q in pts if (q[0] < cx if left else q[0] > cx) and q[1] < part), default=b[1])
        h = part - foot
        lo, hi = (-10000, cx) if left else (cx, 10000)
        # the leg's direction, from the middles of its stroke at two heights
        def mid(y):
            xs = [x for x in M.crossings(flat, y) if lo < x < hi]
            if len(xs) < 2:
                raise SystemExit("old Hangul: no leg to cut short")
            return (xs[0] + xs[1]) / 2
        y0, y1 = foot + 0.3 * h, foot + 0.6 * h
        dx_per_y = (mid(y1) - mid(y0)) / (y1 - y0)
        # the end of the leg (its round cap and a little more) moves up the leg by half
        # the leg's height, and the leg below where it now ends goes
        end = path_op(ops, box(lo, -10000, hi, foot + 0.2 * h), pathops.PathOp.INTERSECTION)
        lift = 0.5 * h
        end = M.transformed(end, 1.0, dx_per_y * lift, 1.0, lift)
        rest = path_op(ops, box(lo, -10000, hi, foot + 0.6 * h), pathops.PathOp.DIFFERENCE)
        return path_op(rest, end, pathops.PathOp.UNION)

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
        """Flat vowel letters one under the other, in order from the top. Two araea
        stand side by side (ᆢ)."""
        if atoms == ["ARAEA", "ARAEA"]:
            return row(atoms, gap=0.5)
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
    # the gap between the two stems of ㅐ, as a share of ㄱ's height (what row takes)
    ae = M.flattened(shape("AE"))
    aeb = M.bounds(ae)
    xs = M.crossings(ae, aeb[1] + 0.15 * (aeb[3] - aeb[1]))
    ae_gap = (xs[2] - xs[1]) / ref_h if len(xs) >= 4 else 0.3
    ref_tall, ref_flat = shape("A"), shape("O")

    def consonant(atoms, box):
        """In the fixed places (the default forms): fitted to the box at ㄱ's scale."""
        return place(row(atoms), box, ref_consonant)

    def consonant_at(atoms, role, cls, f):
        """Where and as large as the designer draws the modern letter it takes after
        (consonant_template): scaled so that letter would fill its box's height, then
        narrowed (to at most half) if it is wider than the box. Falls back to the class
        boxes."""
        t = consonant_template(atoms, role)
        if role == "L":
            box = boxes.get(("i", t, cls, f))
            model = MODERN_INITIALS[t]
            fallback = boxes[("initial", cls, f)]
        else:
            box = boxes.get(("f", t, cls))
            model = MODERN_FINALS[t]
            fallback = boxes[("final", cls)]
        if box is None:
            return consonant(atoms, fallback)
        mb = M.bounds(row(consonant_atoms(model, letters)))
        k = (box[3] - box[1]) / (mb[3] - mb[1])
        # every letter stands in the one place for its class (the designer's own places
        # differ letter to letter, as handwriting does), at the size of its model
        size = box
        box = (fallback[0], fallback[1], fallback[2], fallback[3])
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        half_w, half_h = (size[2] - size[0]) / 2, (size[3] - size[1]) / 2
        box = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
        ops = row(atoms)
        b = M.bounds(ops)
        # across and up are fitted apart, as the designer squeezes a letter to its place
        # (ㄱ of 그 is wide and low), but never more than 1.8 times apart
        kx = (box[2] - box[0]) / (b[2] - b[0])
        ky = (box[3] - box[1]) / (b[3] - b[1])
        kx = min(max(kx, ky / 1.8), ky * 1.8)
        if len(atoms) > 1:
            kx = min(kx, (box[2] - box[0]) * 1.1 / (b[2] - b[0]))
        out = M.transformed(ops, kx, 0.0, ky, 0.0)
        out = weight(out, stroke * (1 - kx), stroke * (1 - ky))
        ob = M.bounds(out)
        return M.transformed(out, 1.0, (box[0] + box[2]) / 2 - (ob[0] + ob[2]) / 2,
                             1.0, (box[1] + box[3]) / 2 - (ob[1] + ob[3]) / 2)

    def scaled(ops, box, k, kx=None):
        """ops scaled by k (across by kx, when given, but never past the box's width),
        stroke given back, centred in box."""
        b = M.bounds(ops)
        kx = k if kx is None else kx
        kx = min(kx, (box[2] - box[0]) / (b[2] - b[0]))
        out = M.transformed(ops, kx, 0.0, k, 0.0)
        out = weight(out, stroke * (1 - kx), stroke * (1 - k))
        ob = M.bounds(out)
        return M.transformed(out, 1.0, (box[0] + box[2]) / 2 - (ob[0] + ob[2]) / 2,
                             1.0, (box[1] + box[3]) / 2 - (ob[1] + ob[3]) / 2)

    def vowel(atoms, tall_box, flat_box):
        """In the fixed places (the default forms): fitted to the boxes."""
        talls = [a for a in atoms if a in TALL]
        flats = [a for a in atoms if a in FLAT]
        out = []
        if flats:
            out += place(stack(flats), flat_box, ref_flat)
        if talls:
            out += place(row(talls, gap=0.05), tall_box, ref_tall)
        return out

    def vowel_at(atoms, f, cls):
        """Where the designer sets the modern vowel it takes after (vowel_template), at
        that vowel's scale. The letters fall in three runs, in the order written:
          flat letters before any upright one (ㅗ of ㅘ) go under the initial, as wide
            as the model's flat letter, the run no taller than the box allows (ᆂ);
          upright letters (ㅏ ㅑ ㅣ) stand to the right, as tall as the model's
            upright letter, a clear gap between two of them (ᆝ);
          flat letters after an upright one (ㅗ of ᅶ, ㅡ of ᆜ) sit small under it, the
            upright letters drawn up to make room.
        Falls back to the class boxes."""
        t = vowel_template(atoms)
        model = vowel_atoms(MODERN_VOWELS[t])
        first_tall = next((n for n, a in enumerate(atoms) if a in TALL), len(atoms))
        before = [a for a in atoms[:first_tall] if a in FLAT]
        talls = [a for a in atoms if a in TALL]
        after = [a for a in atoms[first_tall:] if a in FLAT]
        whole = boxes.get(("v", t, f, "all"))
        if whole is None:
            return vowel(atoms, boxes.get(("tall", cls, f)), boxes.get(("flat", cls, f)))
        flat_box = boxes.get(("v", t, f, "flat"), whole) if talls else whole
        tall_box = boxes.get(("v", t, f, "tall"), whole) if before else whole
        out = []
        model_flat = [a for a in model if a in FLAT]
        model_tall = [a for a in model if a in TALL]
        k_flat = None
        if model_flat:
            rb = M.bounds(shape(model_flat[0]))
            k_flat = (flat_box[2] - flat_box[0]) / (rb[2] - rb[0])
        if before:
            ops = stack(before)
            ob = M.bounds(ops)
            k = min(k_flat, (flat_box[3] - flat_box[1]) * 1.3 / (ob[3] - ob[1]))
            out += scaled(ops, flat_box, k)
        if talls:
            ref = shape(model_tall[0] if model_tall else "I")
            rb = M.bounds(ref)
            k = (tall_box[3] - tall_box[1]) / (rb[3] - rb[1])
            box = tall_box
            if after:
                # the upright letters keep the upper two thirds of the box
                h = box[3] - box[1]
                box = (box[0], box[3] - 0.66 * h, box[2], box[3])
                k *= 0.66
            # two upright letters may run a little wider than the model's one
            wide_box = box if len(talls) == 1 else (box[0] - 0.12 * (box[2] - box[0]), box[1], box[2], box[3])
            # stems as far apart as the two stems of ㅐ
            uprights = scaled(row(talls, gap=ae_gap), wide_box, k)
            out += uprights
            if after:
                stem = M.bounds(uprights)
                ops = stack(after)
                ob = M.bounds(ops)
                kf = (k_flat or k) * 0.6
                h = tall_box[3] - tall_box[1]
                below = (stem[0] - 0.1 * h, tall_box[1], stem[2] + 0.1 * h, tall_box[1] + 0.3 * h)
                out += scaled(ops, below, min(kf, (below[3] - below[1]) / (ob[3] - ob[1])))
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
                    put(f"{name}.L{c}{int(f)}", consonant_at(atoms, "L", c, f), wide, 0)
        elif role == "V":
            for f in (False, True):
                put(f"{name}.V{int(f)}", vowel_at(atoms, f, cls), 0, -wide)
        else:
            for c in range(3):
                put(f"{name}.T{c}", consonant_at(atoms, "T", c, True), 0, -wide)
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
