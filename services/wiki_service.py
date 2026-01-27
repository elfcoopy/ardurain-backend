import wikipedia
from wikipedia.exceptions import DisambiguationError, PageError
from typing import Dict, Any, List
from utils.text_utils import clean_text


def get_wiki_page(plant_name: str):
    try:
        return wikipedia.page(plant_name, auto_suggest=True, redirect=True)
    except DisambiguationError as e:
        # try the first suggestion
        try:
            return wikipedia.page(e.options[0], auto_suggest=True, redirect=True)
        except:
            return None
    except PageError:
        # fallback to the first word (genus sometimes helps)
        try:
            return wikipedia.page(plant_name.split()[0], auto_suggest=True, redirect=True)
        except:
            return None
    except:
        return None


def _clean_categories(cats: List[str], limit: int = 60) -> List[str]:
    out: List[str] = []

    for c in cats or []:
        s = (c or "").strip()
        if not s:
            continue

        s_low = s.lower()

        # Filter out noisy meta categories (Wikipedia maintenance)
        if any(x in s_low for x in [
            "articles",
            "pages",
            "all stub",
            "stub articles",
            "cs1",
            "wikidata",
            "use dmy dates",
            "use mdy dates",
            "coordinates",
            "commons category",
            "short description",
            "good articles",
            "webarchive",
            "harvnb",
            "citation",
            "all articles",
            "unknown parameter",
        ]):
            continue

        out.append(s)
        if len(out) >= limit:
            break

    return out


def get_wiki_info(plant_name: str) -> Dict[str, Any]:
    """
    Returns:
    - description_short (2 sentences)
    - description_long (10 sentences)
    - wiki_url
    - wiki_images (up to 3)
    - wiki_categories (filtered, up to 60)
    - wiki_title
    - summary_for_tags (TITLE + categories + text) for inference
    """
    page = get_wiki_page(plant_name)
    if page is None:
        return {
            "description_short": "No description available.",
            "description_long": "No description available.",
            "wiki_url": "",
            "wiki_images": [],
            "wiki_categories": [],
            "wiki_title": "",
            "summary_for_tags": "",
        }

    title = getattr(page, "title", "") or ""

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

    # Images
    wiki_images: List[str] = []
    try:
        for url in page.images:
            lower = url.lower()

            if not (
                lower.endswith(".jpg")
                or lower.endswith(".jpeg")
                or lower.endswith(".png")
                or lower.endswith(".webp")
            ):
                continue

            if any(x in lower for x in ["logo", "icon", "commons-logo", "wikimedia", "poweredby", "edit-icon"]):
                continue

            wiki_images.append(url)
            if len(wiki_images) >= 3:
                break
    except:
        wiki_images = []

    # Categories
    cats: List[str] = []
    try:
        cats = _clean_categories(getattr(page, "categories", []) or [], limit=60)
    except:
        cats = []

    # ✅ IMPORTANT: feed better hints into inference
    # Title + categories + description => much better cold/region detection
    cats_text = " ".join([c.lower() for c in cats])
    summary_for_tags = f"{title}\n{cats_text}\n{desc_long}".strip()

    # cap size (avoid huge payloads)
    summary_for_tags = summary_for_tags[:4000]

    return {
        "description_short": desc_short,
        "description_long": desc_long,
        "wiki_url": getattr(page, "url", ""),
        "wiki_images": wiki_images,
        "wiki_categories": cats,
        "wiki_title": title,
        "summary_for_tags": summary_for_tags,
    }
