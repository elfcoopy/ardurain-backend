import os
import requests
from typing import Dict, Any, List
from utils.text_utils import dedup_preserve_order

# =========================
# CONFIG
# =========================
PLANTNET_API_KEY = "2b10MZKP3Jl1Gt8NsY295l4wJO"  # keep your key local
PROJECT = "all"
PLANTNET_URL = f"https://my-api.plantnet.org/v2/identify/{PROJECT}?api-key={PLANTNET_API_KEY}"

def _extract_urls_deep(obj: Any) -> List[str]:
    urls: List[str] = []

    def rec(o: Any):
        if isinstance(o, dict):
            for _, v in o.items():
                if isinstance(v, (dict, list)):
                    rec(v)
                else:
                    if isinstance(v, str):
                        s = v.strip()
                        if s.startswith("http") and any(
                            s.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]
                        ):
                            urls.append(s)
        elif isinstance(o, list):
            for it in o:
                rec(it)

    rec(obj)
    return urls


def identify_plant(image_path: str) -> Dict[str, Any] | None:
    """
    Calls PlantNet and returns:
    - scientific name
    - common names
    - score
    - plantnet_images (best effort)
    """
    with open(image_path, "rb") as img:
        files = [("images", (os.path.basename(image_path), img, "image/jpeg"))]
        data = {"organs": ["leaf"]}

        response = requests.post(
            PLANTNET_URL,
            files=files,
            data=data,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

    if not result.get("results"):
        return None

    top = result["results"][0]
    species = top.get("species", {})

    scientific = (
        species.get("scientificNameWithoutAuthor")
        or species.get("scientificName")
        or "Unknown"
    )
    common = species.get("commonNames", []) or []
    score = top.get("score") or 0.0

    common = [str(x) for x in common if str(x).strip()]

    plantnet_images = dedup_preserve_order(_extract_urls_deep(top))[:5]

    return {
        "scientific_name": str(scientific),
        "common_names": common,
        "score": float(score),
        "plantnet_images": plantnet_images,
    }
