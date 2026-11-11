"""How often the initial and a ㅗ/ㅛ-type vowel are drawn as one contour."""
import sys, collections
sys.path.insert(0, "/home/lumi/programming/RiderProjects/LumiFoundry/fonts/kkomi-mono/tools")
from fontTools.ttLib import TTFont
import make_mono as M, hangul_fill as H
tt = TTFont(sys.argv[1]); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
INI = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
VO = {8: "ㅗ", 9: "ㅘ", 10: "ㅙ", 11: "ㅚ", 12: "ㅛ", 13: "ㅜ", 18: "ㅡ"}
cnt = collections.defaultdict(lambda: [0, 0]); ex = collections.defaultdict(list)
for cp in range(H.BASE, H.BASE + 11172):
    i, v, f = H.decompose(cp)
    if v not in VO or cp not in cmap: continue
    ops = M.record(gs, cmap[cp])
    if M.bounds(ops) is None: continue
    cs = M.polygon_points_ops(ops)
    gb = M.bounds(ops)
    # the vowel bar: widest contour
    bar = max(cs, key=lambda q: M.bounds(q)[2] - M.bounds(q)[0])
    b = M.bounds(bar)
    joined = (b[3] - b[1]) > 0.55 * (gb[3] - gb[1]) if not f else (b[3] - b[1]) > 330
    cnt[(i, v)][0] += 1; cnt[(i, v)][1] += joined
    if joined: ex[i].append(chr(cp))
for i in range(19):
    row = [f"{VO[v]} {cnt[(i,v)][1]}/{cnt[(i,v)][0]}" for v in VO if cnt[(i, v)][0]]
    print(INI[i], " ".join(row), "".join(ex[i][:12]))
