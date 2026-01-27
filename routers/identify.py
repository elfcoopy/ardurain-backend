from fastapi import APIRouter, UploadFile, File, Request
from datetime import datetime, timezone
import os
import json

from services.plantnet_service import identify_plant
from services.wiki_service import get_wiki_info
from services.wikidata_service import infer_primary_and_traits
from services.moisture_service import compute_moisture, compute_climate
from utils.text_utils import dedup_preserve_order

PLANT_IMAGES_DIR = "plant_images"

router = APIRouter()


@router.post("/identify_plant")
async def identify_plant_endpoint(request: Request, file: UploadFile = File(...)):
    # Save uploaded image
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
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

    scientific = info.get("scientific_name", "Unknown")
    common_names = info.get("common_names", []) or []

    # Wikipedia info (rich text + images + url)
    wiki = get_wiki_info(scientific)

    # Primary category + traits
    primary, traits, reasoning = infer_primary_and_traits(
        scientific_name=scientific,
        wiki_hint=wiki.get("summary_for_tags", ""),
    )

    # Moisture (existing)
    moisture_min, moisture_max, moisture_target, moisture_mods = compute_moisture(primary, traits)

    # Climate (NEW: temp/humidity)
    (
        temp_min,
        temp_max,
        temp_target,
        hum_min,
        hum_max,
        hum_target,
        climate_mods,
    ) = compute_climate(primary, traits)

    # Build image URL for uploaded image
    base_url = str(request.base_url).rstrip("/")
    image_url = f"{base_url}/images/{filename}"

    # Extra images: PlantNet first + Wikipedia fallback
    extra_images = dedup_preserve_order(
        (info.get("plantnet_images", []) or []) + (wiki.get("wiki_images", []) or [])
    )[:5]

    data = {
        "success": True,

        # Names
        "plant": scientific,
        "common_names": common_names,

        # Classification model
        "category_primary": primary,
        "traits": traits,

        # Backward compatible
        "category": primary,

        # Moisture targets
        "moisture_min": moisture_min,
        "moisture_max": moisture_max,
        "moisture_target": moisture_target,

        # Climate targets
        "temp_min": temp_min,
        "temp_max": temp_max,
        "temp_target": temp_target,
        "humidity_min": hum_min,
        "humidity_max": hum_max,
        "humidity_target": hum_target,

        # Meta
        "timestamp": timestamp,
        "image_url": image_url,
        "confidence": round(float(info.get("score", 0.0) or 0.0), 3),

        # Rich info for UI
        "description_short": wiki.get("description_short", "No description available."),
        "description_long": wiki.get("description_long", "No description available."),
        "wiki_url": wiki.get("wiki_url", ""),
        "extra_images": extra_images,

        # Debug helpers (keep during development)
        "category_reasoning": reasoning,
        "trait_modifiers_applied": moisture_mods,
        "climate_modifiers_applied": climate_mods,
    }

    # Save JSON alongside image
    json_path = os.path.join(PLANT_IMAGES_DIR, f"plant_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(data, jf, indent=4, ensure_ascii=False)

    return data
