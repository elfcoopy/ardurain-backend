from typing import Dict, Tuple, List


def clamp_int(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))


def midpoint(a: int, b: int) -> int:
    return int(round((a + b) / 2))


# =========================
# Moisture base categories
# =========================
PRIMARY_MOISTURE_BASE: Dict[str, Tuple[int, int]] = {
    "desert": (10, 25),
    "mediterranean": (20, 40),
    "temperate_cold": (25, 45),
    "temperate": (25, 45),
    "grassland": (25, 45),
    "savanna": (25, 45),

    "houseplant": (35, 55),

    "subtropical": (40, 65),
    "tropical": (45, 70),
    "rainforest": (60, 85),

    "wetland": (75, 92),
    "bog": (80, 95),
    "aquatic": (85, 98),

    "coastal": (35, 60),

    # cold-ish buckets
    "alpine": (30, 55),
    "arctic": (25, 50),

    # missing bucket your classifier may return
    "fern": (60, 85),

    # optional alias bucket (if you add boreal trait)
    "boreal": (25, 45),  # treat like temperate_cold
}

DEFAULT_PRIMARY = "houseplant"
DEFAULT_RANGE = PRIMARY_MOISTURE_BASE[DEFAULT_PRIMARY]


# =========================
# Moisture modifiers (small)
# =========================
TRAIT_MODIFIERS: Dict[str, Dict[str, int]] = {
    "cactus": {"min": -5, "max": -5, "target": -6},
    "succulent": {"min": -4, "max": -4, "target": -5},
    "xerophyte": {"min": -4, "max": -4, "target": -5},
    "drought_tolerant": {"min": -3, "max": -3, "target": -3},

    "hydrophyte": {"min": +6, "max": +6, "target": +6},
    "wetland_plant": {"min": +5, "max": +5, "target": +5},
    "bog_plant": {"min": +5, "max": +6, "target": +6},

    # epiphytes/orchids: airy media but consistent moisture
    "epiphyte": {"min": +2, "max": +2, "target": +2},
    "orchid": {"min": +2, "max": +2, "target": +2},

    # carnivorous plants tend to like moist substrate
    "carnivorous": {"min": +6, "max": +6, "target": +6},
}


def compute_moisture(primary: str, traits: List[str]) -> Tuple[int, int, int, List[str]]:
    base_min, base_max = PRIMARY_MOISTURE_BASE.get(primary, DEFAULT_RANGE)
    target = midpoint(base_min, base_max)

    applied: List[str] = []
    mn, mx, tg = base_min, base_max, target

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


# =========================
# Climate (Temp + Humidity)
# =========================
# These are "ideal ambient" bands meant for warnings, not greenhouse precision.

PRIMARY_TEMP_BASE_C: Dict[str, Tuple[int, int]] = {
    "arctic": (-5, 12),
    "alpine": (0, 18),
    "temperate_cold": (5, 20),
    "boreal": (5, 20),

    "temperate": (10, 28),
    "mediterranean": (12, 30),
    "grassland": (10, 30),
    "savanna": (16, 35),
    "desert": (18, 40),

    "houseplant": (18, 28),

    "subtropical": (18, 32),
    "tropical": (20, 34),
    "rainforest": (22, 35),

    "wetland": (15, 30),
    "bog": (10, 25),
    "aquatic": (15, 30),

    "coastal": (12, 28),
    "fern": (18, 28),
}

PRIMARY_HUM_BASE: Dict[str, Tuple[int, int]] = {
    "arctic": (20, 50),
    "alpine": (25, 55),
    "temperate_cold": (30, 60),
    "boreal": (30, 60),

    "temperate": (35, 65),
    "mediterranean": (30, 55),
    "grassland": (30, 60),
    "savanna": (25, 55),
    "desert": (15, 40),

    "houseplant": (40, 70),

    "subtropical": (45, 75),
    "tropical": (55, 85),
    "rainforest": (70, 95),

    "wetland": (60, 90),
    "bog": (70, 95),
    "aquatic": (60, 90),

    "coastal": (45, 80),
    "fern": (60, 90),
}

CLIMATE_TRAIT_MODS: Dict[str, Dict[str, int]] = {
    # Hotter/drier
    "cactus": {"tmin": +2, "tmax": +4, "hmin": -10, "hmax": -10},
    "succulent": {"tmin": +1, "tmax": +3, "hmin": -8, "hmax": -8},
    "xerophyte": {"tmin": +1, "tmax": +3, "hmin": -8, "hmax": -8},
    "drought_tolerant": {"tmin": +0, "tmax": +2, "hmin": -5, "hmax": -5},

    # Wetter / humid-loving
    "wetland_plant": {"tmin": 0, "tmax": 0, "hmin": +5, "hmax": +8},
    "bog_plant": {"tmin": 0, "tmax": 0, "hmin": +8, "hmax": +10},
    "hydrophyte": {"tmin": 0, "tmax": 0, "hmin": +8, "hmax": +10},

    # Epiphytes/orchids: prefer higher humidity, moderate temp
    "epiphyte": {"tmin": 0, "tmax": 0, "hmin": +8, "hmax": +10},
    "orchid": {"tmin": 0, "tmax": 0, "hmin": +8, "hmax": +10},

    # Carnivorous plants: often humid/moist environments
    "carnivorous": {"tmin": 0, "tmax": 0, "hmin": +10, "hmax": +10},

    # Coastal: tolerate humidity + wind; keep modest humidity bump
    "coastal": {"tmin": 0, "tmax": 0, "hmin": +3, "hmax": +5},

    # Cold hints
    "arctic": {"tmin": -2, "tmax": -2, "hmin": 0, "hmax": 0},
    "alpine": {"tmin": -1, "tmax": -1, "hmin": 0, "hmax": 0},
    "cold_hardy": {"tmin": -1, "tmax": -1, "hmin": 0, "hmax": 0},
    "boreal": {"tmin": -1, "tmax": -1, "hmin": 0, "hmax": 0},
}


def compute_climate(primary: str, traits: List[str]) -> Tuple[int, int, int, int, int, int, List[str]]:
    tmin, tmax = PRIMARY_TEMP_BASE_C.get(primary, PRIMARY_TEMP_BASE_C["houseplant"])
    hmin, hmax = PRIMARY_HUM_BASE.get(primary, PRIMARY_HUM_BASE["houseplant"])

    applied: List[str] = []

    for t in traits:
        mod = CLIMATE_TRAIT_MODS.get(t)
        if not mod:
            continue
        tmin += mod.get("tmin", 0)
        tmax += mod.get("tmax", 0)
        hmin += mod.get("hmin", 0)
        hmax += mod.get("hmax", 0)
        applied.append(
            f"{t}(t{mod.get('tmin',0)},{mod.get('tmax',0)} h{mod.get('hmin',0)},{mod.get('hmax',0)})"
        )

    # Clamp to sensible bounds
    if tmax < tmin:
        tmax = tmin
    tmin = clamp_int(tmin, -30, 60)
    tmax = clamp_int(tmax, -30, 60)

    if hmax < hmin:
        hmax = hmin
    hmin = clamp_int(hmin, 0, 100)
    hmax = clamp_int(hmax, 0, 100)

    ttarget = midpoint(tmin, tmax)
    htarget = midpoint(hmin, hmax)

    return tmin, tmax, ttarget, hmin, hmax, htarget, applied
