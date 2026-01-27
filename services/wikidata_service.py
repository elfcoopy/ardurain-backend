import requests
from datetime import datetime
from typing import Dict, Any, Tuple, List

from utils.cache_utils import load_cache, save_cache
from utils.text_utils import dedup_preserve_order

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIDATA_CACHE_FILE = "plant_traits_cache.json"


# =========================
# Wikidata fetch + caching
# =========================
def wikidata_search_entity(scientific_name: str) -> str:
    params = {
        "action": "wbsearchentities",
        "search": scientific_name,
        "language": "en",
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": "ArduRain/1.0 (plant project)"}
    r = requests.get(WIKIDATA_API, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    results = data.get("search", [])
    if not results:
        return ""
    return results[0].get("id", "") or ""


def wikidata_get_trait_labels(qid: str) -> List[str]:
    if not qid:
        return []

    # Keep this conservative (fast + reliable)
    query = f"""
    SELECT ?valLabel WHERE {{
      VALUES ?plant {{ wd:{qid} }}

      OPTIONAL {{ ?plant wdt:P3833 ?val . }}   # growth habit
      OPTIONAL {{ ?plant wdt:P31   ?val . }}   # instance of
      OPTIONAL {{ ?plant wdt:P279  ?val . }}   # subclass of
      OPTIONAL {{ ?plant wdt:P171  ?val . }}   # parent taxon (helps: cactus family etc.)

      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 120
    """

    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "ArduRain/1.0 (plant project)",
    }
    r = requests.get(
        WIKIDATA_SPARQL,
        params={"query": query},
        headers=headers,
        timeout=25,
    )
    r.raise_for_status()
    js = r.json()

    out: List[str] = []
    for b in js.get("results", {}).get("bindings", []):
        lbl = b.get("valLabel", {}).get("value", "")
        if lbl:
            out.append(lbl.lower())

    return list(dict.fromkeys(out))


def get_wikidata_traits(scientific_name: str) -> Dict[str, Any]:
    cache = load_cache(WIKIDATA_CACHE_FILE)
    key = scientific_name.strip().lower()

    if key in cache:
        return cache[key]

    traits = {"qid": "", "labels": [], "fetched_at": datetime.now().isoformat()}

    try:
        qid = wikidata_search_entity(scientific_name)
        traits["qid"] = qid
        if qid:
            traits["labels"] = wikidata_get_trait_labels(qid)
    except:
        pass

    cache[key] = traits
    save_cache(WIKIDATA_CACHE_FILE, cache)
    return traits


# =========================
# Classification helpers
# =========================
def _has_any(text: str, *words: str) -> bool:
    return any(w in text for w in words)


def _add_trait(traits: List[str], reasoning: List[str], name: str, why: str) -> None:
    if name not in traits:
        traits.append(name)
        reasoning.append(f"trait: {name} ({why})")


def _add_score(scores: Dict[str, int], reasoning: List[str], key: str, delta: int, why: str) -> None:
    scores[key] = scores.get(key, 0) + delta
    reasoning.append(f"primary +{delta} {key} ({why})")


# =========================
# Main inference
# =========================
def infer_primary_and_traits(scientific_name: str, wiki_hint: str) -> Tuple[str, List[str], List[str]]:
    """
    Returns:
      primary_category: str
      traits: List[str]
      reasoning: List[str]
    """

    reasoning: List[str] = []
    traits: List[str] = []

    wd = get_wikidata_traits(scientific_name)
    labels_text = " ".join(wd.get("labels", [])).lower()
    wiki_text = (wiki_hint or "").lower()
    combined = (labels_text + " " + wiki_text).strip()

    # -------------------------
    # TRAITS (stackable)
    # -------------------------
    # Dry traits
    if _has_any(combined, "cactus", "cactaceae"):
        _add_trait(traits, reasoning, "cactus", "keyword")
    if _has_any(combined, "succulent", "crassulaceae", "echeveria", "sedum", "aloe"):
        _add_trait(traits, reasoning, "succulent", "keyword")
    if _has_any(combined, "xerophyte", "xerophytic"):
        _add_trait(traits, reasoning, "xerophyte", "keyword")
    if _has_any(combined, "drought tolerant", "drought-tolerant", "arid", "semi-arid", "semiarid"):
        _add_trait(traits, reasoning, "drought_tolerant", "keyword")

    # Wet traits
    if _has_any(combined, "hydrophyte", "water plant", "aquatic plant"):
        _add_trait(traits, reasoning, "hydrophyte", "keyword")
    if _has_any(combined, "wetland", "marsh", "swamp", "fen"):
        _add_trait(traits, reasoning, "wetland_plant", "keyword")
    if _has_any(combined, "bog", "peat", "mire"):
        _add_trait(traits, reasoning, "bog_plant", "keyword")

    # Cold / high altitude traits
    if _has_any(combined, "arctic", "tundra", "polar"):
        _add_trait(traits, reasoning, "arctic", "keyword")
    if _has_any(combined, "alpine", "subalpine", "montane", "high elevation", "high-elevation"):
        _add_trait(traits, reasoning, "alpine", "keyword")
    if _has_any(combined, "boreal", "taiga"):
        _add_trait(traits, reasoning, "boreal", "keyword")
    if _has_any(combined, "frost", "freeze", "freezing", "cold-hardy", "cold hardy", "hardy", "subzero", "snow"):
        _add_trait(traits, reasoning, "cold_hardy", "keyword")

    # Growth-form traits (kept as traits only — NOT a primary bucket)
    if _has_any(combined, "fern", "pteridophyte"):
        _add_trait(traits, reasoning, "fern", "keyword")
    if _has_any(combined, "tree"):
        _add_trait(traits, reasoning, "tree", "keyword")
    if _has_any(combined, "shrub"):
        _add_trait(traits, reasoning, "shrub", "keyword")
    if _has_any(combined, "woody", "woody perennial"):
        _add_trait(traits, reasoning, "woody", "keyword")

    # Indoor hint (houseplant should only win if explicit)
    explicit_houseplant = _has_any(combined, "houseplant", "indoor plant", "potted plant")
    if explicit_houseplant:
        _add_trait(traits, reasoning, "houseplant", "explicit indoor")

    # -------------------------
    # PRIMARY CATEGORY scoring
    # -------------------------
    # IMPORTANT: must match keys in moisture_service PRIMARY_MOISTURE_BASE
    PRIMARY_KEYS = [
        "arctic",
        "alpine",
        "temperate_cold",
        "temperate",
        "mediterranean",
        "desert",
        "grassland",
        "savanna",
        "subtropical",
        "tropical",
        "rainforest",
        "wetland",
        "bog",
        "aquatic",
        "coastal",
        "houseplant",
    ]

    DEFAULT_PRIMARY = "houseplant"
    scores: Dict[str, int] = {k: 0 for k in PRIMARY_KEYS}

    # ---- EXTREMELY strong cold signals ----
    if _has_any(combined, "arctic", "tundra", "polar"):
        _add_score(scores, reasoning, "arctic", 12, "cold biome keyword")
    if _has_any(combined, "alpine", "subalpine", "montane", "high elevation", "high-elevation"):
        _add_score(scores, reasoning, "alpine", 10, "mountain keyword")
    if _has_any(combined, "boreal", "taiga"):
        _add_score(scores, reasoning, "temperate_cold", 8, "boreal/taiga keyword")
    if _has_any(combined, "glacial", "permafrost", "subzero", "snowfield", "fellfield"):
        _add_score(scores, reasoning, "arctic", 10, "extreme cold keyword")
    if _has_any(combined, "frost", "freeze", "freezing", "snow", "ice"):
        _add_score(scores, reasoning, "temperate_cold", 5, "cold condition keyword")

    # ---- Wet environments ----
    if _has_any(combined, "aquatic", "water plant", "hydrophyte"):
        _add_score(scores, reasoning, "aquatic", 10, "aquatic keyword")
    if _has_any(combined, "bog", "peat", "mire"):
        _add_score(scores, reasoning, "bog", 9, "bog keyword")
    if _has_any(combined, "wetland", "marsh", "swamp", "fen"):
        _add_score(scores, reasoning, "wetland", 8, "wetland keyword")

    # ---- Humid tropics ----
    if _has_any(combined, "rainforest"):
        _add_score(scores, reasoning, "rainforest", 8, "rainforest keyword")
    if _has_any(combined, "tropical"):
        _add_score(scores, reasoning, "tropical", 6, "tropical keyword")
    if _has_any(combined, "subtropical"):
        _add_score(scores, reasoning, "subtropical", 5, "subtropical keyword")

    # ---- Dry climates ----
    if _has_any(combined, "desert"):
        _add_score(scores, reasoning, "desert", 7, "desert keyword")
    if _has_any(combined, "arid", "semi-arid", "semiarid"):
        _add_score(scores, reasoning, "desert", 4, "arid keyword")
    if _has_any(combined, "mediterranean"):
        _add_score(scores, reasoning, "mediterranean", 5, "mediterranean keyword")

    # ---- Open habitats ----
    if _has_any(combined, "grassland", "prairie", "steppe", "meadow"):
        _add_score(scores, reasoning, "grassland", 4, "grassland/meadow keyword")
    if _has_any(combined, "savanna", "savannah"):
        _add_score(scores, reasoning, "savanna", 4, "savanna keyword")

    # ---- Coastal ----
    if _has_any(combined, "coastal", "shore", "dune", "seashore", "salt spray", "saline"):
        _add_score(scores, reasoning, "coastal", 5, "coastal keyword")

    # ---- Temperate general ----
    if _has_any(combined, "temperate"):
        _add_score(scores, reasoning, "temperate", 3, "temperate keyword")

    # ---- Indoor/houseplant (ONLY if explicit) ----
    if explicit_houseplant:
        _add_score(scores, reasoning, "houseplant", 9, "explicit indoor keyword")
    else:
        # Prevent houseplant from winning by accident
        scores["houseplant"] -= 2

    # ---- Trait nudges (small) ----
    if any(t in traits for t in ["cactus", "succulent", "xerophyte", "drought_tolerant"]):
        _add_score(scores, reasoning, "desert", 3, "dry traits")
    if "wetland_plant" in traits:
        _add_score(scores, reasoning, "wetland", 2, "wetland trait")
    if "bog_plant" in traits:
        _add_score(scores, reasoning, "bog", 2, "bog trait")
    if "hydrophyte" in traits:
        _add_score(scores, reasoning, "aquatic", 2, "hydrophyte trait")
    if "arctic" in traits:
        _add_score(scores, reasoning, "arctic", 3, "arctic trait")
    if "alpine" in traits:
        _add_score(scores, reasoning, "alpine", 3, "alpine trait")
    if "cold_hardy" in traits:
        _add_score(scores, reasoning, "temperate_cold", 2, "cold_hardy trait")

    # Fern trait should push toward wetter/humid *but not a primary bucket*
    if "fern" in traits:
        _add_score(scores, reasoning, "rainforest", 1, "fern trait -> humid bias")
        _add_score(scores, reasoning, "wetland", 1, "fern trait -> moist bias")

    # Choose best
    primary = max(scores.items(), key=lambda kv: kv[1])[0]
    if scores.get(primary, 0) <= 0:
        primary = DEFAULT_PRIMARY
        reasoning.append("primary fallback: houseplant (no strong signals found)")

    traits = dedup_preserve_order(traits)
    return primary, traits, reasoning
