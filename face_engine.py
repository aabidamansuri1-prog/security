"""Face detection (OpenCV Haar cascade) + recognition (OpenCV LBPH)."""
import os
import glob
import shutil
import tempfile
import cv2
import numpy as np
import config


class FaceEngine:
    def __init__(self):
        self.detector = self._load_cascade()
        if not hasattr(cv2, "face"):
            raise RuntimeError("cv2.face missing. Run: pip uninstall opencv-python -y && "
                               "pip install opencv-contrib-python")
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(radius=2, neighbors=8, grid_x=8, grid_y=8)
        self.trained = False
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self.load_or_train()

    @staticmethod
    def _load_cascade():
        """Load the Haar cascade. OpenCV's C++ file functions fail on some Windows
        paths (Store Python, user names with spaces/special chars, OneDrive), so we
        try several strategies, including copying the XML to a plain C:\\ folder."""
        name = "haarcascade_frontalface_default.xml"
        sources = [p for p in (os.path.join(config.BASE_DIR, name),
                               os.path.join(cv2.data.haarcascades, name)) if os.path.isfile(p)]
        # 1) direct load
        for p in sources:
            clf = cv2.CascadeClassifier(p)
            if not clf.empty():
                return clf
        # 2) copy to a simple ASCII-only folder and load from there
        safe_dirs = [os.environ.get("PUBLIC", r"C:\Users\Public"),
                     os.environ.get("ProgramData", r"C:\ProgramData"), "C:\\",
                     tempfile.gettempdir()]
        for p in sources:
            for d in safe_dirs:
                try:
                    dst = os.path.join(d, "cctv_" + name)
                    shutil.copyfile(p, dst)
                    clf = cv2.CascadeClassifier(dst)
                    if not clf.empty():
                        return clf
                except Exception:
                    pass
        # 3) parse from memory
        for p in sources:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    xml = f.read()
                fs = cv2.FileStorage(xml, cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY)
                clf = cv2.CascadeClassifier()
                if clf.read(fs.getFirstTopLevelNode()):
                    return clf
            except Exception:
                pass
        raise RuntimeError("Could not load the face detector. Move the whole project folder "
                           "to C:\\cctv_security (no spaces) and run it from there.")

    # ---------- detection ----------
    def detect(self, gray):
        faces = self.detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=6,
                                               minSize=(70, 70))
        return [tuple(int(v) for v in f) for f in faces]

    def preprocess(self, gray, box):
        x, y, w, h = box
        face = gray[y:y + h, x:x + w]
        face = cv2.resize(face, config.FACE_SIZE)
        return self.clahe.apply(face)

    # ---------- recognition ----------
    def predict(self, face):
        """Return (user_id or None, confidence). None => unregistered."""
        if not self.trained:
            return None, 999.0
        uid, conf = self.recognizer.predict(face)
        if conf <= config.RECOGNITION_THRESHOLD:
            return int(uid), float(conf)
        return None, float(conf)

    # ---------- training ----------
    def save_sample(self, user_id, face, index):
        d = os.path.join(config.FACES_DIR, str(user_id))
        os.makedirs(d, exist_ok=True)
        ok, buf = cv2.imencode(".png", face)
        if ok:
            buf.tofile(os.path.join(d, f"{index:03d}.png"))

    def train(self):
        images, labels = [], []
        for d in glob.glob(os.path.join(config.FACES_DIR, "*")):
            if not os.path.isdir(d) or not os.path.basename(d).isdigit():
                continue
            uid = int(os.path.basename(d))
            for f in glob.glob(os.path.join(d, "*.png")):
                img = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                img = cv2.resize(img, config.FACE_SIZE)
                images.append(img); labels.append(uid)
                images.append(cv2.flip(img, 1)); labels.append(uid)  # mirror augmentation
        if not images:
            self.trained = False
            if os.path.exists(config.MODEL_PATH):
                os.remove(config.MODEL_PATH)
            return False
        self.recognizer.train(images, np.array(labels))
        self.trained = True
        return True

    def load_or_train(self):
        # Always retrain from stored samples: fast and guarantees consistency.
        self.train()
