from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from routers.identify import router as identify_router
from routers.telemetry import router as telemetry_router

# =========================
# CONFIG
# =========================
PLANT_IMAGES_DIR = "plant_images"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict later if you want
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Health check (useful for uptime pings + debugging)
@app.get("/health")
async def health():
    return {"ok": True}

os.makedirs(PLANT_IMAGES_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=PLANT_IMAGES_DIR), name="images")

# Routers
app.include_router(identify_router)
app.include_router(telemetry_router)
