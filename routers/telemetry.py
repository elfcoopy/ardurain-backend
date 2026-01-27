from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any
from threading import Lock
from datetime import datetime, timezone

router = APIRouter()

class TelemetryUpdate(BaseModel):
    device_id: str = Field(..., min_length=1)
    soil: int = Field(..., ge=0, le=100)
    temp: float
    humidity: float
    pump_on: bool

class DeviceConfig(BaseModel):
    device_id: str = Field(..., min_length=1)
    moisture_min: int = Field(..., ge=0, le=100)
    moisture_max: int = Field(..., ge=0, le=100)
    moisture_target: int = Field(..., ge=0, le=100)

_TELEMETRY_LATEST: Dict[str, Dict[str, Any]] = {}
_DEVICE_CONFIG: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()


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


@router.post("/device/config/set")
async def device_config_set(payload: DeviceConfig):
    if payload.moisture_max < payload.moisture_min:
        raise HTTPException(status_code=400, detail="moisture_max must be >= moisture_min")

    now = datetime.now(timezone.utc).isoformat()
    data = payload.model_dump()
    data["ts"] = now

    with _LOCK:
        _DEVICE_CONFIG[payload.device_id] = data

    return {"success": True, "stored": data}


@router.get("/device/config")
async def device_config_get(device_id: str):
    with _LOCK:
        data = _DEVICE_CONFIG.get(device_id)

    if not data:
        return {"success": False, "error": "No config set for this device_id yet."}

    return {"success": True, "config": data}
