import requests
from datetime import datetime
from typing import Dict, Any, Tuple, List

from utils.cache_utils import load_cache, save_cache
from utils.text_utils import dedup_preserve_order

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIDATA_CACHE_FILE = "plant_traits_cache.json"

def wikidata_search_entity(scientific_name: str) -> str:
    params = {
        "action": "wbsearchentities",
        "search": scientific_name,
        "language": "en",
        "format": "json",
        "limit": 1
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

      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 60
    """

    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "ArduRain/1.0 (plant project)"
    }
    r = requests.get(
        WIKIDATA_SPARQL,
        params={"query": query},
        headers=headers,
        timeout=25
    )
    r.raise_for_status()
    js = r.json()

    out = []
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


def _has_any(text: str, *words: str) -> bool:
    return any(w in text for w in words)


def infer_primary_and_traits(scientific_name: str, wiki_hint: str) -> Tuple[str, List[str], List[str]]:
    """
    Returns:
      primary_category: str
      traits: List[str]
      reasoning: List[str]   (debug)
    """
    reasoning: List[str] = []
    traits: List[str] = []

    wd = get_wikidata_traits(scientific_name)
    labels_text = " ".join(wd.get("labels", [])).lower()
    wiki_text = (wiki_hint or "").lower()
    combined = (labels_text + " " + wiki_text).strip()

    # -------- traits (can stack) --------
    if _has_any(combined, "cactus", "cactaceae"):
        traits.append("cactus")
        reasoning.append("trait: cactus")
    if _has_any(combined, "succulent"):
        traits.append("succulent")
        reasoning.append("trait: succulent")
    if _has_any(combined, "xerophyte"):
        traits.append("xerophyte")
        reasoning.append("trait: xerophyte")
    if _has_any(combined, "drought-tolerant", "drought tolerant", "arid"):
        traits.append("drought_tolerant")
        reasoning.append("trait: drought_tolerant")

    if _has_any(combined, "epiphyte", "epiphytic"):
        traits.append("epiphyte")
        reasoning.append("trait: epiphyte")
    if _has_any(combined, "orchid", "orchidaceae"):
        traits.append("orchid")
        reasoning.append("trait: orchid")
    if _has_any(combined, "carnivorous plant", "carnivorous", "drosera", "nepenthes", "sarracenia"):
        traits.append("carnivorous")
        reasoning.append("trait: carnivorous")

    if _has_any(combined, "woody", "woodland shrub", "woody perennial"):
        traits.append("woody")
        reasoning.append("trait: woody")
    if _has_any(combined, "tree"):
        traits.append("tree")
        reasoning.append("trait: tree")
    if _has_any(combined, "shrub"):
        traits.append("shrub")
        reasoning.append("trait: shrub")

    if _has_any(combined, "hydrophyte", "water plant"):
        traits.append("hydrophyte")
        reasoning.append("trait: hydrophyte")
    if _has_any(combined, "wetland", "marsh", "swamp"):
        traits.append("wetland_plant")
        reasoning.append("trait: wetland_plant")

    # -------- primary category (choose best via scoring) --------
    PRIMARY_MOISTURE_BASE = {
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

    scores: Dict[str, int] = {k: 0 for k in PRIMARY_MOISTURE_BASE.keys()}

    if _has_any(combined, "aquatic", "water plant", "hydrophyte"):
        scores["aquatic"] += 5
        reasoning.append("primary score +5 aquatic")
    if _has_any(combined, "bog", "peat", "mire"):
        scores["bog"] += 5
        reasoning.append("primary score +5 bog")
    if _has_any(combined, "wetland", "marsh", "swamp"):
        scores["wetland"] += 4
        reasoning.append("primary score +4 wetland")
    if _has_any(combined, "fern", "pteridophyte"):
        scores["fern"] += 4
        reasoning.append("primary score +4 fern")

    if _has_any(combined, "rainforest"):
        scores["rainforest"] += 4
        reasoning.append("primary score +4 rainforest")
    if _has_any(combined, "tropical"):
        scores["tropical"] += 3
        reasoning.append("primary score +3 tropical")
    if _has_any(combined, "subtropical"):
        scores["subtropical"] += 3
        reasoning.append("primary score +3 subtropical")
    if _has_any(combined, "mediterranean"):
        scores["mediterranean"] += 3
        reasoning.append("primary score +3 mediterranean")
    if _has_any(combined, "desert"):
        scores["desert"] += 3
        reasoning.append("primary score +3 desert")

    if _has_any(combined, "houseplant", "indoor plant"):
        scores["houseplant"] += 3
        reasoning.append("primary score +3 houseplant")

    if _has_any(combined, "temperate"):
        scores["temperate"] += 2
        reasoning.append("primary score +2 temperate")

    if "cactus" in traits or "succulent" in traits or "xerophyte" in traits:
        scores["desert"] += 1
        reasoning.append("primary score +1 desert (traits)")
    if "wetland_plant" in traits or "hydrophyte" in traits:
        scores["wetland"] += 1
        reasoning.append("primary score +1 wetland (traits)")
    if "epiphyte" in traits or "orchid" in traits:
        scores["tropical"] += 1
        reasoning.append("primary score +1 tropical (traits)")

    primary = max(scores.items(), key=lambda kv: kv[1])[0]
    if scores.get(primary, 0) == 0:
        primary = DEFAULT_PRIMARY
        reasoning.append("primary fallback: houseplant")

    traits = dedup_preserve_order(traits)
    return primary, traits, reasoning
