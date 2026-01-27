import wikipedia
from wikipedia.exceptions import DisambiguationError, PageError
from typing import Dict, Any, List
from utils.text_utils import clean_text


def get_wiki_page(plant_name: str):
    try:
        return wikipedia.page(plant_name, auto_suggest=True, redirect=True)
    except DisambiguationError as e:
        try:
            return wikipedia.page(e.options[0], auto_suggest=True, redirect=True)
        except:
            return None
    except PageError:
        try:
            return wikipedia.page(plant_name.split()[0], auto_suggest=True, redirect=True)
        except:
            return None
    except:
        return None


def _clean_categories(cats: List[str]) -> List[str]:
    out = []
    for c in cats or []:
        s = (c or "").strip()
        if not s:
            continue
        s_low = s.lower()

        # Filter out noisy meta categories
        if any(x in s_low for x in [
            "articles", "pages", "all stub", "cs1", "wikidata",
            "use dmy dates", "use mdy dates", "coordinates",
            "commons category", "short description", "good articles",
        ]):
            continue

        out.append(s)
        if len(out) >= 20:
            break
    return out


def get_wiki_info(plant_name: str) -> Dict[str, Any]:
    """
    Returns:
    - description_short (2 sentences)
    - description_long (10 sentences)
    - wiki_url
    - wiki_images (up to 3)
    - wiki_categories (filtered, up to 20)
    - summary_for_tags (text + categories, for inference)
    """
    page = get_wiki_page(plant_name)
    if page is None:
        return {
            "description_short": "No description available.",
            "description_long": "No description available.",
            "wiki_url": "",
            "wiki_images": [],
            "wiki_categories": [],
            "summary_for_tags": "",
        }

    title = page.title

    try:
        desc_short = wikipedia.summary(title, sentences=2)
    except:
        desc_short = "No description available."

    try:
        desc_long = wikipedia.summary(title, sentences=10)
    except:
        desc_long = desc_short

    desc_short = clean_text(desc_short)
    desc_long = clean_text(desc_long)

    # Images (keep your existing filtering)
    wiki_images = []
    try:
        for url in page.images:
            lower = url.lower()

            if not (lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".png") or lower.endswith(".webp")):
                continue

            if any(x in lower for x in ["logo", "icon", "commons-logo", "wikimedia", "poweredby", "edit-icon"]):
                continue

            wiki_images.append(url)
            if len(wiki_images) >= 3:
                break
    except:
        wiki_images = []

    # Categories (NEW)
    cats = []
    try:
        cats = _clean_categories(getattr(page, "categories", []) or [])
    except:
        cats = []

    # This is what your classifier reads.
    # We append categories because they often contain strong habitat/climate hints.
    cats_text = " ".join([c.lower() for c in cats])
    summary_for_tags = (desc_long[:2000] + " " + cats_text).strip()

    return {
        "description_short": desc_short,
        "description_long": desc_long,
        "wiki_url": getattr(page, "url", ""),
        "wiki_images": wiki_images,
        "wiki_categories": cats,
        "summary_for_tags": summary_for_tags,
    }
