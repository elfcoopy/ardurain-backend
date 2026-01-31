from fastapi import APIRouter, UploadFile, File, Request
from datetime import datetime, timezone
import os
import json
from typing import Optional

from services.plantnet_service import identify_plant
from services.wiki_service import get_wiki_info
from services.wikidata_service import infer_primary_and_traits
from services.moisture_service import compute_moisture, compute_climate
from utils.text_utils import dedup_preserve_order

PLANT_IMAGES_DIR = "plant_images"

router = APIRouter()


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _guess_ext(upload: UploadFile) -> str:
    """
    Decide the best extension for saving the uploaded image.
    - Prefer the original filename extension if present.
    - Otherwise fall back to content-type mapping.
    """
    # 1) From filename
    ext = ""
    if upload.filename:
        _, ext = os.path.splitext(upload.filename)
        ext = (ext or "").lower().strip()

    if ext in {".jpg", ".jpeg", ".png", ".heic", ".heif"}:
        return ext

    # 2) From content type
    ct = (upload.content_type or "").lower()
    if ct in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if ct == "image/png":
        return ".png"
    if ct in {"image/heic", "image/heif"}:
        return ".heic"

    # 3) Default fallback
    return ".jpg"


def _is_heic(upload: UploadFile, ext: str) -> bool:
    ct = (upload.content_type or "").lower()
    return ext in {".heic", ".heif"} or ct in {"image/heic", "image/heif"}


def _try_convert_heic_to_jpg(src_path: str, dst_path: str) -> bool:
    """
    Tries to convert HEIC/HEIF -> JPEG.
    Returns True if converted, False otherwise.
    Requires pillow + pillow-heif on the server.
    """
    try:
        from PIL import Image  # type: ignore
        try:
            import pillow_heif  # type: ignore
            pillow_heif.register_heif_opener()
        except Exception:
            # If pillow-heif isn't available, PIL probably can't open HEIC
            pass

        with Image.open(src_path) as im:
            im = im.convert("RGB")
            im.save(dst_path, format="JPEG", quality=92, optimize=True)
        return True
    except Exception:
        return False


@router.post("/identify_plant")
async def identify_plant_endpoint(request: Request, file: UploadFile = File(...)):
    _ensure_dir(PLANT_IMAGES_DIR)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

    # Read bytes
    contents = await file.read()
    if not contents:
        return {"success": False, "error": "Empty upload."}

    # Pick extension based on upload
    ext = _guess_ext(file)

    # Save initial file
    filename = f"plant_{timestamp}{ext}"
    image_path = os.path.join(PLANT_IMAGES_DIR, filename)

    with open(image_path, "wb") as f:
        f.write(contents)

    # If HEIC/HEIF, try convert to JPG for PlantNet compatibility
    if _is_heic(file, ext):
        jpg_filename = f"plant_{timestamp}.jpg"
        jpg_path = os.path.join(PLANT_IMAGES_DIR, jpg_filename)

        converted = _try_convert_heic_to_jpg(image_path, jpg_path)
        if converted:
            # Prefer the converted jpg for identification and for serving in UI
            filename = jpg_filename
            image_path = jpg_path
        else:
            # Don't silently fail: PlantNet often rejects HEIC.
            return {
                "success": False,
                "error": (
                    "PlantNet error: iOS uploaded HEIC/HEIF image and the server "
                    "could not convert it to JPG. Install server deps: "
                    "pip install pillow pillow-heif, or configure the iOS picker "
                    "to export JPEG/PNG."
                ),
            }

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

    # Climate (temp/humidity)
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
