"""Fills Hangul syllables a font maps but never draws, from the syllables it does draw.

The font must draw each jamo as its own contours (Kkomi does). A syllable is split into
its upper part (initial and vowel) and its final consonant: the final is the lowest few
contours, as many as that final usually has in the font.

A missing syllable (initial I, vowel V, final F) is built in the first way that works:
1. upper part of a drawn syllable with I and V and some other final, plus the final F
   taken from a drawn syllable with vowel V (so it sits where finals sit under V);
2. a drawn syllable with V and F and another initial, with its initial swapped for I
   taken from a drawn syllable whose vowel sits the same way (right, below or both);
3. a drawn syllable with I and V and no final, pressed down into the upper part's
   height, plus the final F as in 1;
4. (no final) a drawn syllable with I and V and some final, with the final removed and
   the upper part stretched back to full height.

The initial is told from the vowel by shape: the vowel's upright strokes are tall and
stand in the right part of the syllable, its crossbar is the lowest wide stroke, and small
pieces touching either belong to the vowel too. Everything else is the initial. A
split is trusted only when the initial has as many contours as it usually has.
Anything else stays undrawn, and the build leaves it to the fallback font.
"""
import collections

import make_mono as M

BASE = 0xAC00


def decompose(cp):
    n = cp - BASE
    return n // 588, (n % 588) // 28, n % 28


def compose(i, v, f):
    return BASE + i * 588 + v * 28 + f


def center_y(contour):
    b = M.bounds(contour)
    return (b[1] + b[3]) / 2


def flatten(contours):
    return [op for c in contours for op in c]


def shift(contours, dx, dy):
    return [M.transformed(c, 1.0, dx, 1.0, dy) for c in contours]


RIGHT = {0, 1, 2, 3, 4, 5, 6, 7, 20}        # ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅣ
BELOW = {8, 12, 13, 17, 18}                  # ㅗ ㅛ ㅜ ㅠ ㅡ
BOTH = {9, 10, 11, 14, 15, 16, 19}           # ㅘ ㅙ ㅚ ㅝ ㅞ ㅟ ㅢ


# double finals and their two consonants as single finals: ㄳ ㄵ ㄶ ㄺ ㄻ ㄼ ㄽ ㄾ ㄿ ㅀ ㅄ
DOUBLE_FINAL = {3: (1, 19), 5: (4, 22), 6: (4, 27), 9: (8, 1), 10: (8, 16), 11: (8, 17),
                12: (8, 19), 13: (8, 25), 14: (8, 26), 15: (8, 27), 18: (17, 19)}

# double initials and the single one they repeat: ㄲ ㄸ ㅃ ㅆ ㅉ
DOUBLE_OF = {1: 0, 4: 3, 8: 7, 10: 9, 13: 12}


def vowel_class(v):
    return 0 if v in RIGHT else 1 if v in BELOW else 2


def touches(a, b, slack=25):
    return not (a[2] + slack < b[0] or b[2] + slack < a[0] or a[3] + slack < b[1] or b[3] + slack < a[1])


def fill(glyph_set, cmap, weight):
    """Returns {glyph name: outline} for the syllables that could be built.
    weight(ops, dx, dy) thickens strokes (negative thins), used after squeezing."""
    drawn = {}
    for cp in range(BASE, BASE + 11172):
        name = cmap.get(cp)
        if name is None:
            continue
        ops = M.record(glyph_set, name)
        if M.bounds(ops) is not None:
            drawn[cp] = M.polygon_points_ops(ops)

    # How many contours each final has: a syllable with a final against the same
    # syllable without one. A final's parts can rise high (the cap of ㅎ or ㅊ), so the
    # count is not read off a height line.
    low_counts = collections.defaultdict(collections.Counter)
    for cp, cs in drawn.items():
        i, v, f = decompose(cp)
        if f and compose(i, v, 0) in drawn:
            low_counts[f][len(cs) - len(drawn[compose(i, v, 0)])] += 1
    final_size = {f: cnt.most_common(1)[0][0] for f, cnt in low_counts.items()}

    def split(cp):
        """Upper part and final: the final is the contours whose tops are lowest."""
        cs = drawn[cp]
        f = decompose(cp)[2]
        if not f:
            return cs, []
        k = final_size.get(f, 1)
        if k <= 0 or k >= len(cs):
            return cs, []
        order = sorted(cs, key=lambda c: M.bounds(c)[3])
        return order[k:], order[:k]

    def counts_right(cp):
        """The final splits off whole: every final contour lies below every upper one
        (by centre), and when the open syllable is drawn, the counts add up."""
        i, v, f = decompose(cp)
        upper, low = split(cp)
        if not low or not upper:
            return False
        if compose(i, v, 0) in drawn and len(drawn[cp]) - len(drawn[compose(i, v, 0)]) != len(low):
            return False
        return max(center_y(c) for c in low) < min(center_y(c) for c in upper)

    # the usual height of each final, to catch a final drawn in one stroke with the vowel
    heights = collections.defaultdict(list)
    for cp in drawn:
        f = decompose(cp)[2]
        if f and counts_right(cp):
            b = M.bounds(flatten(split(cp)[1]))
            heights[f].append(b[3] - b[1])
    final_height = {f: sorted(h)[len(h) // 2] for f, h in heights.items()}

    def clean(cp):
        """True when the final splits off as it usually does: as many contours as usual,
        and no taller than usual (a taller one has taken the vowel along)."""
        f = decompose(cp)[2]
        if not counts_right(cp):
            return False
        b = M.bounds(flatten(split(cp)[1]))
        return b[3] - b[1] <= final_height.get(f, 1e9) * 1.3

    by_iv = collections.defaultdict(list)    # (i, v) -> drawn syllables with a final
    by_vf = collections.defaultdict(list)    # (v, f) -> drawn syllables
    by_f = collections.defaultdict(list)
    for cp in drawn:
        i, v, f = decompose(cp)
        if f:
            by_iv[(i, v)].append(cp)
            by_vf[(v, f)].append(cp)
            by_f[f].append(cp)

    def final_from(v, f):
        donors = [cp for cp in by_vf.get((v, f), []) if clean(cp)]
        if not donors:
            donors = [cp for cp in by_f.get(f, []) if clean(cp)]
        if not donors:
            return None
        upper, low = split(donors[0])
        return upper, low

    def attach(upper, final_donor, slot):
        """Sets the donor's final into `slot`, the box the replaced final filled: tops
        aligned, centred across, pressed down to the slot's height when it is taller."""
        _, d_low = final_donor
        dl = M.bounds(flatten(d_low))
        top = slot[3]
        # a taller final reaches further down, and is pressed only past the descent limit
        lowest = -230
        ky = 1.0
        if top - (dl[3] - dl[1]) < lowest:
            ky = (top - lowest) / (dl[3] - dl[1])
        cx = (slot[0] + slot[2]) / 2
        placed = M.transformed(flatten(d_low), 1.0, cx - (dl[0] + dl[2]) / 2, ky, top - ky * dl[3])
        if ky < 0.98:
            placed = weight(placed, 0.0, 68 * (1 - ky))
        return upper + M.polygon_points_ops(placed)

    def parts(cp):
        """(initial, vowel, final) contour lists of a drawn syllable, or None."""
        upper, low = split(cp)
        if len(upper) < 2:
            return None
        ub = M.bounds(flatten(upper))
        uw, uh = ub[2] - ub[0], ub[3] - ub[1]
        bb = {id(k): M.bounds(k) for k in upper}
        cls = vowel_class(decompose(cp)[1])
        vowel = []
        if cls in (0, 2):
            vowel += [k for k in upper if bb[id(k)][3] - bb[id(k)][1] > 0.5 * uh
                      and (bb[id(k)][0] + bb[id(k)][2]) / 2 > ub[0] + 0.45 * uw]
        if cls in (1, 2):
            # the crossbar, often drawn in one stroke with its short upright
            flat = [k for k in upper if bb[id(k)][2] - bb[id(k)][0] > 0.5 * uw
                    and bb[id(k)][3] - bb[id(k)][1] < 0.6 * uh
                    and (bb[id(k)][1] + bb[id(k)][3]) / 2 < ub[1] + 0.5 * uh]
            if flat:
                vowel.append(min(flat, key=lambda k: bb[id(k)][1]))
        if not vowel:
            return None
        stems = [q for q in vowel if bb[id(q)][3] - bb[id(q)][1] > 0.5 * uh]
        if stems:
            # short flat strokes just left of an upright (the bars of ㅓ ㅕ ㅔ ㅖ)
            sx = min(bb[id(q)][0] for q in stems)
            for k in upper:
                b = bb[id(k)]
                if not any(k is q for q in vowel) and b[3] - b[1] < 0.3 * uh \
                        and b[2] - b[0] < 0.4 * uw and b[2] >= sx - 60:
                    vowel.append(k)
        grown = True
        while grown:
            grown = False
            for k in upper:
                if any(k is q for q in vowel):
                    continue
                b = bb[id(k)]
                small = b[3] - b[1] < 0.4 * uh and b[2] - b[0] < 0.4 * uw
                if small and any(touches(b, bb[id(q)]) for q in vowel):
                    vowel.append(k)
                    grown = True
        initial = [k for k in upper if not any(k is q for q in vowel)]
        if not initial:
            return None
        v_idx = decompose(cp)[1]
        if v_idx in RIGHT and v_idx != 20:
            # a vowel narrower than it should be has lost a stroke to the initial
            vb = M.bounds(flatten(vowel))
            need = 0.35 if v_idx in (1, 3, 5, 7) else 0.22
            if vb[2] - vb[0] < need * uw:
                return None
        if stems:
            # an initial reaching past the vowel's upright has swallowed part of the vowel
            if max(bb[id(k)][2] for k in initial) > min(bb[id(q)][0] for q in stems) + 20:
                return None
        return initial, vowel, low

    split_parts = {}
    init_counts = collections.defaultdict(collections.Counter)
    for cp in drawn:
        pr = parts(cp)
        split_parts[cp] = pr
        if pr:
            init_counts[decompose(cp)[0]][len(pr[0])] += 1
    init_size = {i: cnt.most_common(1)[0][0] for i, cnt in init_counts.items()}

    def trusted(cp):
        pr = split_parts.get(cp)
        return pr is not None and len(pr[0]) == init_size.get(decompose(cp)[0], -1) \
            and (not decompose(cp)[2] or clean(cp))

    by_v_f_all = collections.defaultdict(list)
    by_i = collections.defaultdict(list)
    for cp in drawn:
        i, v, f = decompose(cp)
        # a double initial splits badly (its second half looks like a vowel stroke):
        # never take one apart, build it from the single instead
        if trusted(cp) and i not in DOUBLE_OF:
            by_v_f_all[(v, f)].append(cp)
            by_i[i].append(cp)

    def aspect(contours):
        b = M.bounds(flatten(contours))
        return (b[2] - b[0]) / max(1, b[3] - b[1])

    def swap_initial(i, v, f):
        single = DOUBLE_OF.get(i, i)
        sources = [cp for cp in by_i.get(single, [])
                   if vowel_class(decompose(cp)[1]) == vowel_class(v) and bool(decompose(cp)[2]) == bool(f)]
        if not sources:
            return None
        # the closest vowel first, then any
        sources.sort(key=lambda cp: abs(decompose(cp)[1] - v))
        src_init = split_parts[sources[0]][0]
        if i in DOUBLE_OF:
            # two copies side by side, each a little narrower than the single
            sb0 = M.bounds(flatten(src_init))
            w = sb0[2] - sb0[0]
            left = M.transformed(flatten(src_init), 0.8, sb0[0] * 0.2, 1.0, 0.0)
            right = M.transformed(flatten(src_init), 0.8, sb0[0] * 0.2 + w * 0.8 + 20, 1.0, 0.0)
            src_init = M.polygon_points_ops(weight(left + right, 68 * 0.2, 0.0))
        hosts = [cp for cp in by_v_f_all.get((v, f), []) if decompose(cp)[0] != i]
        refinal = False
        if not hosts and f:
            # no syllable with this vowel and final: take one with another final and
            # swap the final as well
            hosts = [cp for (vv, ff), cps in by_v_f_all.items() if vv == v and ff
                     for cp in cps if decompose(cp)[0] != i]
            refinal = True
        if not hosts:
            return None
        a = aspect(src_init)
        host = min(hosts, key=lambda cp: abs(aspect(split_parts[cp][0]) - a))
        h_init, h_vowel, h_low = split_parts[host]
        hb = M.bounds(flatten(h_init))
        sb = M.bounds(flatten(src_init))
        if i in DOUBLE_OF:
            # a double initial needs more room: grow the box to the left
            grow = (hb[2] - hb[0]) * 0.45
            room = hb[0] - 10
            hb = (hb[0] - min(grow, max(0, room)), hb[1], hb[2], hb[3])
        kx = (hb[2] - hb[0]) / (sb[2] - sb[0])
        ky = (hb[3] - hb[1]) / (sb[3] - sb[1])
        # keep the source's proportions within 20 percent
        g = (kx * ky) ** 0.5
        kx = min(max(kx, g / 1.2), g * 1.2)
        ky = min(max(ky, g / 1.2), g * 1.2)
        cx, cy = (hb[0] + hb[2]) / 2, (hb[1] + hb[3]) / 2
        scx, scy = (sb[0] + sb[2]) / 2, (sb[1] + sb[3]) / 2
        placed = M.transformed(flatten(src_init), kx, cx - kx * scx, ky, cy - ky * scy)
        if abs(kx - 1) > 0.02 or abs(ky - 1) > 0.02:
            placed = weight(placed, 68 * (1 - kx), 68 * (1 - ky))
        new_upper = M.polygon_points_ops(placed) + h_vowel
        if refinal:
            donor_f = final_from(v, f)
            if donor_f is None:
                return None
            return attach(new_upper, donor_f, M.bounds(flatten(h_low)))
        return new_upper + h_low

    # how far the designer sets a syllable with a double final above (or below) the same
    # syllable with only its first consonant (않 over 안, 굶 under 굴): the median over
    # the pairs the font draws, for each double final
    rises = collections.defaultdict(list)
    for cp in drawn:
        i, v, f = decompose(cp)
        for g in DOUBLE_FINAL.get(f, ()):
            if compose(i, v, g) in drawn:
                rises[f].append(M.bounds(flatten(drawn[cp]))[3] - M.bounds(flatten(drawn[compose(i, v, g)]))[3])
                break
    double_rise = {f: sorted(r)[len(r) // 2] for f, r in rises.items()}

    out = {}
    stats = collections.Counter()
    for cp in range(BASE, BASE + 11172):
        if cp in drawn or cp not in cmap:
            continue
        i, v, f = decompose(cp)
        built = None
        if f:
            donor_f = final_from(v, f)
            iv = [d for d in by_iv.get((i, v), []) if clean(d)]
            if donor_f and iv:
                # under a double final the initial and vowel stand where the designer
                # set them in a syllable they share. Best is one with another double
                # final on the same first consonant (훑 for 훎): its upper part is taken
                # when it splits cleanly, and the built one is moved so the tops meet.
                # Next is the syllable with only the first consonant (훌, else 훔), with
                # the tops set as far apart as the font sets such pairs (double_rise).
                sib = [compose(i, v, g) for g, parts_g in DOUBLE_FINAL.items()
                       if g != f and parts_g[0] == DOUBLE_FINAL.get(f, (None,))[0]
                       and compose(i, v, g) in drawn]
                single = [compose(i, v, g) for g in DOUBLE_FINAL.get(f, ()) if compose(i, v, g) in drawn]
                iv.sort(key=lambda d: (d not in sib, d not in single))
                upper, low = split(iv[0])
                built = attach(upper, donor_f, M.bounds(flatten(low)))
                top = None
                if sib:
                    top = M.bounds(flatten(drawn[sib[0]]))[3]
                elif single:
                    top = M.bounds(flatten(drawn[single[0]]))[3] + double_rise.get(f, 0.0)
                if top is not None:
                    built = shift(built, 0.0, top - M.bounds(flatten(built))[3])
                    stats["double final set by the designer's own"] += 1
                stats["upper of same initial+vowel"] += 1
            elif (built := swap_initial(i, v, f)) is not None:
                stats["initial swapped"] += 1
            elif donor_f and compose(i, v, 0) in drawn:
                # press the open syllable into the height the upper parts usually have
                plain = drawn[compose(i, v, 0)]
                pb = M.bounds(flatten(plain))
                ref_upper, ref_low = donor_f
                rb = M.bounds(flatten(ref_upper))
                ky = (rb[3] - rb[1]) / (pb[3] - pb[1])
                pressed = M.transformed(flatten(plain), 1.0, 0.0, ky, rb[3] - ky * pb[3])
                stroke = 68
                pressed = weight(pressed, 0.0, stroke * (1 - ky))
                upper = M.polygon_points_ops(pressed)
                built = attach(upper, donor_f, M.bounds(flatten(ref_low)))
                stats["open syllable pressed"] += 1
        else:
            iv = [d for d in by_iv.get((i, v), []) if clean(d)]
            if (built := swap_initial(i, v, 0)) is not None:
                stats["initial swapped"] += 1
            elif iv:
                upper, _ = split(iv[0])
                ub = M.bounds(flatten(upper))
                # stretch down to where open syllables of this vowel end
                opens = [drawn[compose(ii, v, 0)] for ii in range(19) if compose(ii, v, 0) in drawn]
                if opens:
                    bottom = sorted(M.bounds(flatten(o))[1] for o in opens)[len(opens) // 2]
                    ky = (ub[3] - bottom) / (ub[3] - ub[1])
                    stretched = M.transformed(flatten(upper), 1.0, 0.0, ky, ub[3] - ky * ub[3])
                    stretched = weight(stretched, 0.0, 68 * (1 - ky))
                    built = M.polygon_points_ops(stretched)
                    stats["final removed, stretched"] += 1
        if built:
            out[cmap[cp]] = flatten(built)
        else:
            stats["left to the fallback font"] += 1

    # drawn syllables whose final runs much wider than the same final under the same
    # vowel elsewhere: the final is taken from the syllable named beside it
    for ch, donor in REDRAW_FINAL.items():
        cp, dcp = ord(ch), ord(donor)
        if cp not in drawn or dcp not in drawn or not split(cp)[1] or not split(dcp)[1]:
            continue
        upper, low = split(cp)
        _, d_low = split(dcp)
        lb, db = M.bounds(flatten(low)), M.bounds(flatten(d_low))
        out[cmap[cp]] = flatten(attach(upper, (None, d_low), (db[0], lb[1], db[2], lb[3])))
        stats["final redrawn"] += 1
    return out, stats


# 법's ㅂ reaches under the whole vowel, half again as wide as in 업 멉 섭
REDRAW_FINAL = {"법": "업"}
