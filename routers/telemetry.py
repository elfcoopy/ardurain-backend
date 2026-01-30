from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from threading import Lock
from datetime import datetime, timezone

router = APIRouter()

# -------------------------
# Models
# -------------------------
class TelemetryUpdate(BaseModel):
    device_id: str = Field(..., min_length=1)
    soil: int = Field(..., ge=0, le=100)
    temp: float
    humidity: float
    pump_on: bool


class DeviceConfig(BaseModel):
    device_id: str = Field(..., min_length=1)

    # Moisture (0–100)
    moisture_min: int = Field(..., ge=0, le=100)
    moisture_max: int = Field(..., ge=0, le=100)
    moisture_target: int = Field(..., ge=0, le=100)

    # Temp (C) — allow negatives for cold plants
    temp_min: int = Field(18, ge=-50, le=150)
    temp_max: int = Field(28, ge=-50, le=150)
    temp_target: int = Field(23, ge=-50, le=150)

    # Humidity (0–100)
    humidity_min: int = Field(40, ge=0, le=100)
    humidity_max: int = Field(70, ge=0, le=100)
    humidity_target: int = Field(55, ge=0, le=100)


# -------------------------
# In-memory storage
# -------------------------
_TELEMETRY_LATEST: Dict[str, Dict[str, Any]] = {}
_DEVICE_CONFIG: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()


# -------------------------
# Telemetry endpoints
# -------------------------
@router.post("/telemetry/update")
async def telemetry_update(payload: TelemetryUpdate):
    now = datetime.now(timezone.utc).isoformat()
    data = payload.model_dump()
    data["ts"] = now
    with _LOCK:
        _TELEMETRY_LATEST[payload.device_id] = data
    return {"success": True, "stored": data}


@router.get("/telemetry/latest")
async def telemetry_latest(device_id: str):
    with _LOCK:
        data = _TELEMETRY_LATEST.get(device_id)
    if not data:
        return {"success": False, "error": "No telemetry yet for this device_id."}
    return {"success": True, "telemetry": data}


# -------------------------
# Device config endpoints
# -------------------------
@router.post("/device/config/set")
async def device_config_set(payload: DeviceConfig):
    # Validate ordering
    if payload.moisture_max < payload.moisture_min:
        raise HTTPException(status_code=400, detail="moisture_max must be >= moisture_min")
    if payload.moisture_target < payload.moisture_min or payload.moisture_target > payload.moisture_max:
        raise HTTPException(status_code=400, detail="moisture_target must be within [moisture_min, moisture_max]")

    if payload.temp_max < payload.temp_min:
        raise HTTPException(status_code=400, detail="temp_max must be >= temp_min")
    if payload.temp_target < payload.temp_min or payload.temp_target > payload.temp_max:
        raise HTTPException(status_code=400, detail="temp_target must be within [temp_min, temp_max]")

    if payload.humidity_max < payload.humidity_min:
        raise HTTPException(status_code=400, detail="humidity_max must be >= humidity_min")
    if payload.humidity_target < payload.humidity_min or payload.humidity_target > payload.humidity_max:
        raise HTTPException(status_code=400, detail="humidity_target must be within [humidity_min, humidity_max]")

    now = datetime.now(timezone.utc).isoformat()
    data = payload.model_dump()
    data["ts"] = now

    with _LOCK:
        _DEVICE_CONFIG[payload.device_id] = data

    # Return flattened fields too (easy for Arduino parsing)
    return {
        "success": True,
        **data,
        "stored": data,
    }


@router.get("/device/config")
async def device_config_get(device_id: str):
    with _LOCK:
        data = _DEVICE_CONFIG.get(device_id)

    if not data:
        return {"success": False, "error": "No config set for this device_id yet."}

    # Return flattened fields too (easy for Arduino parsing)
    return {
        "success": True,
        **data,
        "config": data,
    }
