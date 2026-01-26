from typing import Dict, Tuple, List
from utils.text_utils import clamp_int

PRIMARY_MOISTURE_BASE: Dict[str, Tuple[int, int]] = {
    "desert": (10, 25),
    "mediterranean": (20, 40),
    "temperate": (25, 45),
    "houseplant": (35, 55),
    "subtropical": (40, 65),
    "tropical": (45, 70),
    "rainforest": (60, 85),
    "fern": (60, 85),
    "wetland": (75, 92),
    "bog": (80, 95),
    "aquatic": (85, 98),
}

DEFAULT_PRIMARY = "houseplant"
DEFAULT_RANGE = PRIMARY_MOISTURE_BASE[DEFAULT_PRIMARY]

TRAIT_MODIFIERS: Dict[str, Dict[str, int]] = {
    "cactus": {"min": -5, "max": -5, "target": -6},
    "succulent": {"min": -4, "max": -4, "target": -5},
    "xerophyte": {"min": -4, "max": -4, "target": -5},
    "drought_tolerant": {"min": -3, "max": -3, "target": -3},

    "hydrophyte": {"min": +6, "max": +6, "target": +6},
    "wetland_plant": {"min": +5, "max": +5, "target": +5},

    "woody": {"min": -1, "max": -1, "target": -1},
    "tree": {"min": -1, "max": -1, "target": -1},
    "shrub": {"min": -1, "max": -1, "target": -1},

    "houseplant": {"min": +0, "max": +0, "target": +0},

    "epiphyte": {"min": +2, "max": +2, "target": +2},
    "orchid": {"min": +2, "max": +2, "target": +2},

    "carnivorous": {"min": +5, "max": +5, "target": +5},
}

def midpoint(a: int, b: int) -> int:
    return int(round((a + b) / 2))


def compute_moisture(primary: str, traits: List[str]):
    base_min, base_max = PRIMARY_MOISTURE_BASE.get(primary, DEFAULT_RANGE)
    target = midpoint(base_min, base_max)

    mn, mx, tg = base_min, base_max, target
    applied = []

    for t in traits:
        mod = TRAIT_MODIFIERS.get(t)
        if not mod:
            continue
        mn += mod.get("min", 0)
        mx += mod.get("max", 0)
        tg += mod.get("target", 0)
        applied.append(f"{t}({mod.get('min',0)},{mod.get('max',0)},{mod.get('target',0)})")

    mn = clamp_int(mn, 0, 100)
    mx = clamp_int(mx, 0, 100)
    if mx < mn:
        mx = mn

    tg = clamp_int(tg, mn, mx)
    return mn, mx, tg, applied
def compute_climate(primary: str, traits: List[str]):
    """
    Returns:
      temp_min, temp_max, temp_target,
      humidity_min, humidity_max, humidity_target,
      applied_debug
    Heuristic, but consistent and good for warnings.
    """
    # Base ranges by primary category
    base = {
        "desert":        {"t": (18, 38), "h": (15, 40)},
        "mediterranean": {"t": (15, 32), "h": (30, 55)},
        "temperate":     {"t": (10, 26), "h": (35, 60)},
        "houseplant":    {"t": (18, 28), "h": (40, 60)},
        "subtropical":   {"t": (18, 30), "h": (50, 70)},
        "tropical":      {"t": (20, 32), "h": (60, 80)},
        "rainforest":    {"t": (20, 30), "h": (70, 90)},
        "fern":          {"t": (16, 28), "h": (60, 85)},
        "wetland":       {"t": (16, 30), "h": (65, 90)},
        "bog":           {"t": (14, 28), "h": (70, 95)},
        "aquatic":       {"t": (18, 30), "h": (70, 95)},
    }

    # fallback
    tmin, tmax = base.get(primary, base["houseplant"])["t"]
    hmin, hmax = base.get(primary, base["houseplant"])["h"]

    applied = []

    # Trait modifiers
    if "cactus" in traits or "succulent" in traits or "xerophyte" in traits:
        hmin -= 8; hmax -= 10
        applied.append("dry_traits(-humidity)")
    if "orchid" in traits or "epiphyte" in traits:
        hmin += 8; hmax += 10
        applied.append("orchid/epiphyte(+humidity)")
    if "carnivorous" in traits:
        hmin += 10; hmax += 10
        applied.append("carnivorous(+humidity)")
    if "wetland_plant" in traits or "hydrophyte" in traits:
        hmin += 6; hmax += 6
        applied.append("wet_traits(+humidity)")

    # Clamp
    tmin = clamp_int(tmin, 0, 100)
    tmax = clamp_int(tmax, 0, 100)
    if tmax < tmin: tmax = tmin

    hmin = clamp_int(hmin, 0, 100)
    hmax = clamp_int(hmax, 0, 100)
    if hmax < hmin: hmax = hmin

    ttarget = midpoint(tmin, tmax)
    htarget = midpoint(hmin, hmax)

    return tmin, tmax, ttarget, hmin, hmax, htarget, applied
def compute_climate(primary: str, traits: List[str]):
    """
    Returns:
      temp_min, temp_max, temp_target,
      humidity_min, humidity_max, humidity_target,
      applied_debug
    Heuristic but consistent (great for warnings + UI ranges).
    """
    base = {
        "desert":        {"t": (18, 38), "h": (15, 40)},
        "mediterranean": {"t": (15, 32), "h": (30, 55)},
        "temperate":     {"t": (10, 26), "h": (35, 60)},
        "houseplant":    {"t": (18, 28), "h": (40, 60)},
        "subtropical":   {"t": (18, 30), "h": (50, 70)},
        "tropical":      {"t": (20, 32), "h": (60, 80)},
        "rainforest":    {"t": (20, 30), "h": (70, 90)},
        "fern":          {"t": (16, 28), "h": (60, 85)},
        "wetland":       {"t": (16, 30), "h": (65, 90)},
        "bog":           {"t": (14, 28), "h": (70, 95)},
        "aquatic":       {"t": (18, 30), "h": (70, 95)},
    }

    tmin, tmax = base.get(primary, base["houseplant"])["t"]
    hmin, hmax = base.get(primary, base["houseplant"])["h"]

    applied = []

    if "cactus" in traits or "succulent" in traits or "xerophyte" in traits:
        hmin -= 8
        hmax -= 10
        applied.append("dry_traits(-humidity)")
    if "orchid" in traits or "epiphyte" in traits:
        hmin += 8
        hmax += 10
        applied.append("orchid/epiphyte(+humidity)")
    if "carnivorous" in traits:
        hmin += 10
        hmax += 10
        applied.append("carnivorous(+humidity)")
    if "wetland_plant" in traits or "hydrophyte" in traits:
        hmin += 6
        hmax += 6
        applied.append("wet_traits(+humidity)")

    tmin = clamp_int(tmin, 0, 100)
    tmax = clamp_int(tmax, 0, 100)
    if tmax < tmin:
        tmax = tmin

    hmin = clamp_int(hmin, 0, 100)
    hmax = clamp_int(hmax, 0, 100)
    if hmax < hmin:
        hmax = hmin

    ttarget = midpoint(tmin, tmax)
    htarget = midpoint(hmin, hmax)

    return tmin, tmax, ttarget, hmin, hmax, htarget, applied
