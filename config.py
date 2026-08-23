# config.py - Complete configuration with all criteria

from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env")

CONFIG = {
    # === COLLECTION TARGETS ===
    "TARGET_REAL": 1000,
    "TARGET_FAKE": 1000,
    "BATCH_SIZE": 25,  # Videos per batch run
    
    # === ACCEPTANCE CRITERIA ===
   "ACCEPTANCE": {
        "MIN_DURATION": 3,  # Was 5
        "MAX_DURATION": 60,
        "MIN_WIDTH": 480,   # Was 854
        "MIN_HEIGHT": 360,  # Was 480
        "MIN_FACE_SIZE_RATIO": 0.05,  # Was 0.15
        "MAX_FACES": 5,     # Was 3
        "MIN_FACES": 1,
        "MIN_LAPLACIAN_VARIANCE": 30,  # Was 100
        "MIN_SSIM": 0.3,
        "MAX_COMPRESSION_SCORE": 0.8,  # Was 0.6
    },
    
    # === PLATFORM CONFIGURATION ===
    "PLATFORMS": {
        "youtube": {"enabled": True, "max_per_day": 200},
        "tiktok": {"enabled": True, "max_per_day": 150},
        "instagram": {"enabled": True, "max_per_day": 100},
    },
    
    # === PATHS ===
    "PATHS": {
        "download": "./downloads",
        "metadata": "./metadata",
        "logs": "./logs",
        "cookies": "./cookies",
    },
    
    # === GOOGLE DRIVE ===
    "DRIVE_FOLDER_ID": os.getenv("DRIVE_FOLDER_ID"),
    
    # === PROXY (optional) ===
    "PROXY": None,  # e.g., "socks5://localhost:1080"
}