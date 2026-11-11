import sys, runpy, collections
sys.path.insert(0, "/home/lumi/programming/RiderProjects/LumiFoundry/fonts/kkomi-mono/tools")
sys.path.insert(0, "experiments/2.0")
sys.argv = ["make_mono_static.py", "../source/KNPSKkomi.otf", "experiments/2.0/comp-Base.ttf", "KNPS Kkomi", "KNPS Kkomi Mono"]
import hangul_fill, compose
orig = hangul_fill.fill
def fill(gs, cmap, weight, **kw):
    if kw:
        return orig(gs, cmap, weight, **kw)
    out, st, info = compose.compose(gs, cmap, weight)
    print("composed", len(out), dict(st))
    return out, collections.Counter({"composed": len(out)})
hangul_fill.fill = fill
runpy.run_path("make_mono_static.py", run_name="__main__")
