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

    query = f"""
    SELECT ?valLabel WHERE {{
      VALUES ?plant {{ wd:{qid} }}

      OPTIONAL {{ ?plant wdt:P3833 ?val . }}   # growth habit
      OPTIONAL {{ ?plant wdt:P31   ?val . }}   # instance of
      OPTIONAL {{ ?plant wdt:P279  ?val . }}   # subclass of
      OPTIONAL {{ ?plant wdt:P171  ?val . }}   # parent taxon

      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 140
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
# Helpers
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


def _is_explicit_indoor(text: str) -> bool:
    # Only treat these as "houseplant" evidence when explicit
    return _has_any(
        text,
        "houseplant",
        "indoor plant",
        "potted plant",
        "grown indoors",
        "cultivated as a houseplant",
        "commonly kept as a houseplant",
    )


def _is_wild_context(text: str) -> bool:
    # A strong signal it is not an indoor “houseplant default”
    return _has_any(
        text,
        "native to",
        "native of",
        "endemic to",
        "found in",
        "occurs in",
        "distributed in",
        "distribution",
        "habitat",
        "wildflower",
        "grows in",
        "naturalised",
        "naturalized",
        "flora of",
        "plants of",
        "vegetation of",
    )


# =========================
# Main inference
# =========================
def infer_primary_and_traits(scientific_name: str, wiki_hint: str) -> Tuple[str, List[str], List[str]]:
    """
    Returns:
      primary_category: str
      traits: List[str]
      reasoning: List[str]

    NOTE: wiki_hint already includes categories (from your wiki_service),
    so this function benefits a lot from terms like:
    "Flora of Spain", "Mediterranean flora", "Alpine plants", etc.
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
    if _has_any(combined, "succulent", "crassulaceae", "aloe", "echeveria", "sedum"):
        _add_trait(traits, reasoning, "succulent", "keyword")
    if _has_any(combined, "xerophyte", "xerophytic"):
        _add_trait(traits, reasoning, "xerophyte", "keyword")
    if _has_any(combined, "drought tolerant", "drought-tolerant", "arid", "semi-arid", "semiarid"):
        _add_trait(traits, reasoning, "drought_tolerant", "keyword")

    # Wet traits
    if _has_any(combined, "hydrophyte", "water plant", "aquatic plant"):
        _add_trait(traits, reasoning, "hydrophyte", "keyword")
    if _has_any(combined, "wetland", "marsh", "swamp", "fen", "riparian"):
        _add_trait(traits, reasoning, "wetland_plant", "keyword")
    if _has_any(combined, "bog", "peat", "mire"):
        _add_trait(traits, reasoning, "bog_plant", "keyword")

    # Cold / altitude traits
    if _has_any(combined, "arctic", "tundra", "polar"):
        _add_trait(traits, reasoning, "arctic", "keyword")
    if _has_any(combined, "alpine", "subalpine", "montane", "high elevation", "high-elevation"):
        _add_trait(traits, reasoning, "alpine", "keyword")
    if _has_any(combined, "boreal", "taiga"):
        _add_trait(traits, reasoning, "boreal", "keyword")
    if _has_any(combined, "cold hardy", "cold-hardy", "frost", "freeze", "freezing", "snow", "subzero"):
        _add_trait(traits, reasoning, "cold_hardy", "keyword")

    # -------------------------
    # PRIMARY CATEGORY SCORING
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
    scores: Dict[str, int] = {k: 0 for k in PRIMARY_KEYS}

    # ---- HARD RULE: houseplant only if explicit ----
    explicit_houseplant = _is_explicit_indoor(combined)
    if explicit_houseplant:
        _add_score(scores, reasoning, "houseplant", 10, "explicit indoor wording")
    else:
        # Push houseplant down by default so it doesn't win accidentally
        scores["houseplant"] -= 6
        reasoning.append("primary -6 houseplant (not explicitly indoor)")

    # If it's clearly wild/native context, penalize houseplant further
    if _is_wild_context(combined):
        scores["houseplant"] -= 6
        reasoning.append("primary -6 houseplant (wild/native context)")

    # ---- COLD ----
    if _has_any(combined, "arctic", "tundra", "polar", "polar desert"):
        _add_score(scores, reasoning, "arctic", 12, "arctic/tundra keywords")
    if _has_any(combined, "alpine", "subalpine", "montane", "mountain", "high elevation", "high-elevation"):
        _add_score(scores, reasoning, "alpine", 10, "alpine/mountain keywords")
    if _has_any(combined, "boreal", "taiga"):
        _add_score(scores, reasoning, "temperate_cold", 8, "boreal/taiga keywords")
    if _has_any(combined, "frost", "freeze", "freezing", "snow", "ice", "subzero"):
        _add_score(scores, reasoning, "temperate_cold", 5, "cold conditions keywords")

    # ---- MEDITERRANEAN / EUROPE DRY SHRUBLAND ----
    # Digitalis obscura is a good example: often Spain + Mediterranean shrublands.
    if _has_any(combined, "mediterranean", "mediterranea", "maquis", "garrigue"):
        _add_score(scores, reasoning, "mediterranean", 10, "mediterranean biome keywords")
    if _has_any(combined, "spain", "iberian", "andalusia", "portugal", "balearic"):
        _add_score(scores, reasoning, "mediterranean", 6, "iberian region keywords")

    # ---- DESERT / ARID ----
    if _has_any(combined, "desert"):
        _add_score(scores, reasoning, "desert", 10, "desert keyword")
    if _has_any(combined, "arid", "semi-arid", "semiarid", "xeric"):
        _add_score(scores, reasoning, "desert", 5, "arid/xeric keywords")
    if any(t in traits for t in ["cactus", "succulent", "xerophyte", "drought_tolerant"]):
        _add_score(scores, reasoning, "desert", 4, "dry traits")

    # ---- WET ----
    if _has_any(combined, "aquatic", "water plant", "hydrophyte"):
        _add_score(scores, reasoning, "aquatic", 10, "aquatic keywords")
    if _has_any(combined, "bog", "peat", "mire"):
        _add_score(scores, reasoning, "bog", 9, "bog keywords")
    if _has_any(combined, "wetland", "marsh", "swamp", "fen", "riparian"):
        _add_score(scores, reasoning, "wetland", 8, "wetland keywords")
    if "hydrophyte" in traits:
        _add_score(scores, reasoning, "aquatic", 2, "hydrophyte trait")
    if "bog_plant" in traits:
        _add_score(scores, reasoning, "bog", 2, "bog trait")
    if "wetland_plant" in traits:
        _add_score(scores, reasoning, "wetland", 2, "wetland trait")

    # ---- TROPICS / HUMID ----
    if _has_any(combined, "rainforest"):
        _add_score(scores, reasoning, "rainforest", 9, "rainforest keyword")
    if _has_any(combined, "tropical", "tropics"):
        _add_score(scores, reasoning, "tropical", 6, "tropical keyword")
    if _has_any(combined, "subtropical"):
        _add_score(scores, reasoning, "subtropical", 5, "subtropical keyword")
    if _has_any(combined, "humid", "high humidity"):
        _add_score(scores, reasoning, "rainforest", 2, "humid hint")

    # ---- COASTAL ----
    if _has_any(combined, "coastal", "shore", "dune", "seashore", "salt spray", "saline", "littoral"):
        _add_score(scores, reasoning, "coastal", 7, "coastal keywords")

    # ---- OPEN HABITATS ----
    if _has_any(combined, "grassland", "prairie", "steppe", "meadow"):
        _add_score(scores, reasoning, "grassland", 7, "grassland keywords")
    if _has_any(combined, "savanna", "savannah"):
        _add_score(scores, reasoning, "savanna", 7, "savanna keywords")

    # ---- TEMPERATE GENERAL ----
    if _has_any(combined, "temperate"):
        _add_score(scores, reasoning, "temperate", 4, "temperate keyword")

    # ---- REGION -> likely climate nudges (lightweight, but helps coverage) ----
    # If it's explicitly "North America / Canada / Rockies" etc, tend colder/continental.
    if _has_any(combined, "canada", "alberta", "saskatchewan", "british columbia", "rocky mountains"):
        _add_score(scores, reasoning, "temperate_cold", 4, "canada/rockies region")

    # Choose best
    primary = max(scores.items(), key=lambda kv: kv[1])[0]
    if scores.get(primary, 0) <= 0:
        # Better fallback than "houseplant": use temperate unless explicitly indoor
        primary = "houseplant" if explicit_houseplant else "temperate"
        reasoning.append(f"primary fallback: {primary} (no strong signals)")

    traits = dedup_preserve_order(traits)
    return primary, traits, reasoning
