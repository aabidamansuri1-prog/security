"""Run: python check_setup.py   -> tells you exactly what is wrong."""
import os, sys
print("Python:", sys.version.split()[0], "| folder:", ascii(os.getcwd()))
try:
    import cv2, flask, numpy
    print("OpenCV:", cv2.__version__, "| cv2.face available:", hasattr(cv2, "face"))
except Exception as e:
    print("MISSING LIBRARY ->", e); print("Run: python -m pip install flask numpy opencv-contrib-python"); sys.exit(1)
xml = os.path.join(os.path.dirname(os.path.abspath(__file__)), "haarcascade_frontalface_default.xml")
print("detector xml in project folder:", os.path.isfile(xml))
from face_engine import FaceEngine
FaceEngine(); print("Face detector loaded OK - you can now run: python app.py")
