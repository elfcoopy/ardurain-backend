from fastapi import APIRouter, UploadFile, File, Request
from datetime import datetime
import os
import json

from services.plantnet_service import identify_plant
from services.wiki_service import get_wiki_info
from services.wikidata_service import infer_primary_and_traits
from services.moisture_service import compute_moisture
from utils.text_utils import dedup_preserve_order
from services.moisture_service import compute_moisture, compute_climate

PLANT_IMAGES_DIR = "plant_images"

router = APIRouter()


@router.post("/identify_plant")
async def identify_plant_endpoint(request: Request, file: UploadFile = File(...)):
    # Save uploaded image
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"plant_{timestamp}.jpg"
    image_path = os.path.join(PLANT_IMAGES_DIR, filename)

    contents = await file.read()
    with open(image_path, "wb") as f:
        f.write(contents)

    # Identify plant via PlantNet
    try:
        info = identify_plant(image_path)
    except Exception as e:
        return {"success": False, "error": f"PlantNet error: {str(e)}"}

    if not info:
        return {"success": False, "error": "Could not identify plant"}

    scientific = info["scientific_name"]
    common_names = info["common_names"]

    # Wikipedia info (rich text + images + url)
    wiki = get_wiki_info(scientific)

    # Primary category + traits (Wikidata + Wikipedia)
    primary, traits, reasoning = infer_primary_and_traits(
        scientific_name=scientific,
        wiki_hint=wiki.get("summary_for_tags", ""),
    )

    moisture_min, moisture_max, moisture_target, applied_mods = compute_moisture(primary, traits)

    temp_min, temp_max, temp_target, hum_min, hum_max, hum_target, climate_applied = compute_climate(primary, traits)

    # Build image URL for uploaded image
    base_url = str(request.base_url).rstrip("/")
    image_url = f"{base_url}/images/{filename}"

    # Extra images:
    # Prefer PlantNet (recency/relevance), then add Wikipedia images as fallback.
    extra_images = dedup_preserve_order(
        (info.get("plantnet_images", []) or []) + (wiki.get("wiki_images", []) or [])
    )[:5]

    data = {
        "success": True,

        # Names
        "plant": scientific,
        "common_names": common_names,

        # New model
        "category_primary": primary,
        "traits": traits,

        # Backward compatible old field
        "category": primary,

        # Moisture targets
        "moisture_min": moisture_min,
        "moisture_max": moisture_max,
        "moisture_target": moisture_target,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "temp_target": temp_target,
        "humidity_min": hum_min,
        "humidity_max": hum_max,
        "humidity_target": hum_target,
        "climate_modifiers_applied": climate_applied,

        # Meta
        "timestamp": timestamp,
        "image_url": image_url,
        "confidence": round(info["score"], 3),

        # Rich info for UI
        "description_short": wiki["description_short"],
        "description_long": wiki["description_long"],
        "wiki_url": wiki["wiki_url"],
        "extra_images": extra_images,

        # Debug helpers
        "category_reasoning": reasoning,
        "trait_modifiers_applied": applied_mods,
    }

    # Save JSON alongside image
    json_path = os.path.join(PLANT_IMAGES_DIR, f"plant_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(data, jf, indent=4, ensure_ascii=False)

    return data
