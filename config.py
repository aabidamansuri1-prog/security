"""Central configuration. Change values here (or via environment variables)."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FACES_DIR = os.path.join(DATA_DIR, "faces")          # registered face samples
EVIDENCE_DIR = os.path.join(DATA_DIR, "evidence")    # alert snapshots
MODEL_PATH = os.path.join(DATA_DIR, "model.yml")     # trained recognizer
DB_PATH = os.path.join(DATA_DIR, "security.db")

# 0 = default webcam, 1 = second camera, or a CCTV/IP stream URL such as
# "rtsp://user:pass@192.168.1.10:554/stream" or a video file path.
_src = os.environ.get("CAMERA_SOURCE", "0")
CAMERA_SOURCE = int(_src) if _src.isdigit() else _src

FRAME_WIDTH = 640
SAMPLES_PER_PERSON = 25      # face images captured during registration
RECOGNITION_THRESHOLD = float(os.environ.get("THRESHOLD", 70))  # LBPH: LOWER = better match
UNKNOWN_FRAMES_TO_ALERT = 6  # consecutive frames with unknown face before alert
ALERT_COOLDOWN_SEC = 10      # minimum gap between two alerts
FACE_SIZE = (200, 200)
