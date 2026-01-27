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
# Helpers
# =========================
def _has_any(text: str, *words: str) -> bool:
    return any(w in text for w in words)


def _is_wild_native(text: str) -> bool:
    return _has_any(
        text,
        "native to",
        "native of",
        "wildflower",
        "perennial",
        "occurs in",
        "found in",
        "distribution",
    )


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
    reasoning: List[str] = []
    traits: List[str] = []

    wd = get_wikidata_traits(scientific_name)
    labels_text = " ".join(wd.get("labels", [])).lower()
    wiki_text = (wiki_hint or "").lower()
    combined = (labels_text + " " + wiki_text).strip()

    # -------------------------
    # TRAITS
    # -------------------------
    if _has_any(combined, "cactus", "cactaceae"):
        _add_trait(traits, reasoning, "cactus", "keyword")
    if _has_any(combined, "succulent", "crassulaceae", "aloe", "echeveria", "sedum"):
        _add_trait(traits, reasoning, "succulent", "keyword")
    if _has_any(combined, "xerophyte", "xerophytic"):
        _add_trait(traits, reasoning, "xerophyte", "keyword")
    if _has_any(combined, "hydrophyte", "aquatic plant"):
        _add_trait(traits, reasoning, "hydrophyte", "keyword")
    if _has_any(combined, "wetland", "marsh", "swamp", "fen"):
        _add_trait(traits, reasoning, "wetland_plant", "keyword")
    if _has_any(combined, "bog", "peat", "mire"):
        _add_trait(traits, reasoning, "bog_plant", "keyword")

    if _has_any(combined, "arctic", "tundra", "polar"):
        _add_trait(traits, reasoning, "arctic", "keyword")
    if _has_any(combined, "alpine", "subalpine", "montane", "high elevation"):
        _add_trait(traits, reasoning, "alpine", "keyword")
    if _has_any(combined, "boreal", "taiga"):
        _add_trait(traits, reasoning, "boreal", "keyword")
    if _has_any(combined, "cold hardy", "frost", "freeze", "snow"):
        _add_trait(traits, reasoning, "cold_hardy", "keyword")

    # -------------------------
    # PRIMARY CATEGORY SCORING
    # -------------------------
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

    # Geographic inference
    if _has_any(
        combined,
        "north america",
        "western north america",
        "great plains",
        "rocky mountains",
        "sagebrush",
        "prairie",
        "steppe",
    ):
        _add_score(scores, reasoning, "grassland", 6, "north american wild habitat")
        _add_score(scores, reasoning, "temperate_cold", 5, "continental climate")

    # Ranunculus & buttercup family
    if _has_any(combined, "ranunculus", "ranunculaceae", "buttercup"):
        _add_score(scores, reasoning, "temperate_cold", 6, "ranunculus genus")
        _add_score(scores, reasoning, "grassland", 4, "wild perennial genus")

    # Strong cold
    if _has_any(combined, "arctic", "tundra", "polar"):
        _add_score(scores, reasoning, "arctic", 12, "cold biome")
    if _has_any(combined, "alpine", "subalpine", "montane"):
        _add_score(scores, reasoning, "alpine", 10, "mountain biome")

    # Penalize houseplant if wild
    if _is_wild_native(combined):
        scores["houseplant"] -= 6
        reasoning.append("primary -6 houseplant (wild native species)")

    # Explicit indoor
    if _has_any(combined, "houseplant", "indoor plant"):
        _add_score(scores, reasoning, "houseplant", 9, "explicit indoor keyword")

    primary = max(scores.items(), key=lambda kv: kv[1])[0]
    if scores.get(primary, 0) <= 0:
        primary = "houseplant"
        reasoning.append("primary fallback: houseplant (no strong signals)")

    traits = dedup_preserve_order(traits)
    return primary, traits, reasoning
