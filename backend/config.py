import os
import shutil
from pathlib import Path

# Base workspace directories
BASE_DIR = Path(__file__).resolve().parent.parent
WATCH_DIR = BASE_DIR / "watch_dir"
OUTPUT_DIR = BASE_DIR / "output_dir"
DATA_DIR = BASE_DIR / ".data"

# Ensure monitored, export, and data directories exist
WATCH_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database migration check
old_db_path = BASE_DIR / "oftolaserr.db"
new_db_path = DATA_DIR / "oftolaserr.db"

if old_db_path.exists() and not new_db_path.exists():
    try:
        shutil.move(str(old_db_path), str(new_db_path))
        print(f"Migrated database from {old_db_path} to {new_db_path}")
    except Exception as e:
        print(f"Failed to migrate database: {e}")

# Database
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{new_db_path}")

# Laser Hardware Configuration
# If COM_MOCK is set, the system will simulate laser communication over serial.
LASER_SERIAL_PORT = os.environ.get("LASER_SERIAL_PORT", "COM_MOCK")
LASER_BAUDRATE = int(os.environ.get("LASER_BAUDRATE", 115200))

# Lens engraving baseline settings
DEFAULT_MARK_DISTANCE_MM = 34.0  # Horizontal distance between the two technical engravings
DEFAULT_SAFETY_MARGIN_MM = 3.0    # Minimum offset from physical lens edge
DEFAULT_BASE_CURVE = 6.0          # Default spherical base curve in diopters (for curvature correction)
DEFAULT_REFRACTIVE_INDEX = 1.6    # Default lens index for radius calculations

# Initial Calibration Constants
# Shift offsets in mm and rotation offset in degrees
DEFAULT_CALIBRATION_X = 0.0
DEFAULT_CALIBRATION_Y = 0.0
DEFAULT_CALIBRATION_ROT = 0.0
DEFAULT_CALIBRATION_SCALE_X = 1.0
DEFAULT_CALIBRATION_SCALE_Y = 1.0
