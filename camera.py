"""Background camera thread: capture -> detect -> recognise -> alert."""
import os
import re
import sys
import time
import json
import threading
from datetime import datetime
import cv2
import numpy as np

import config
import database as db
from face_engine import FaceEngine

GREEN, RED, YELLOW = (0, 200, 0), (0, 0, 255), (0, 215, 255)


def _beep():
    """Server-side beep on Windows (browser also plays an alarm)."""
    if sys.platform.startswith("win"):
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(1800, 250)
        except Exception:
            pass


class SecurityCamera:
    def __init__(self):
        self.engine = FaceEngine()
        self.cap = None
        self.lock = threading.Lock()
        self.jpeg = None
        self.running = False
        self.camera_ok = False
        self.status_text = "Starting..."
        self.unknown_count = 0
        self.last_alert_ts = 0.0
        self.latest_alert = None        # dict(id, time, image)
        self.reg = None                 # registration job
        self.source = self._load_source()
        self.monitoring = True
        self._reopen = False
        self._gen = 0                       # lets stop()/start() replace the loop thread safely
        self.use_server_stream = False      # True = server reads a CCTV/IP URL (Render, public URL only)
        self.browser_label = "Browser camera (this device)"
        self._faces = []                    # faces found in the last processed frame
        self._size = (config.FRAME_WIDTH, 480)
        self.proc_lock = threading.Lock()   # one browser frame processed at a time
        self.last_browser_frame = 0.0       # time of the last frame sent by a browser
        self.names = {u["id"]: u["name"] for u in db.list_users()}

    # ---------- control ----------
    def start(self):
        if self.running:
            return
        self.running = True
        self._gen += 1
        self._reopen = True                 # always open a fresh capture for the new loop
        threading.Thread(target=self._loop, args=(self._gen,), daemon=True).start()

    def stop(self):
        """Stop the server-side capture loop (used when switching to the browser camera)."""
        self.running = False
        self._gen += 1
        self.camera_ok = False

    # ---------- camera source (webcam / CCTV-IP stream / video file) ----------
    SETTINGS = os.path.join(config.DATA_DIR, "settings.json")

    def _load_source(self):
        try:
            with open(self.SETTINGS, encoding="utf-8") as f:
                return json.load(f)["source"]
        except Exception:
            return config.CAMERA_SOURCE

    def set_source(self, src):
        self.source = src
        try:
            with open(self.SETTINGS, "w", encoding="utf-8") as f:
                json.dump({"source": src}, f)
        except OSError:
            pass
        self.camera_ok = False
        self.status_text = "Connecting to new source..."
        self._reopen = True                 # loop thread switches to the new source

    def set_monitoring(self, on):
        self.monitoring = bool(on)
        if not on:
            self.status_text = "Monitoring stopped"

    def source_label(self):
        s = self.source
        if isinstance(s, int):
            return f"Webcam {s}"
        if os.path.isfile(str(s)):
            return "Video file: " + os.path.basename(s)
        return "CCTV / IP stream: " + re.sub(r"//[^@/]*@", "//***@", str(s))   # hide password

    def _open(self):
        src = self.source
        if isinstance(src, int) and sys.platform.startswith("win"):
            cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        elif isinstance(src, str) and re.match(r"^(rtsp|rtmp|http|https)://", src, re.I):
            # network/CCTV stream: give up after 6 s instead of hanging for minutes
            try:
                cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG,
                                       [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 6000,
                                        cv2.CAP_PROP_READ_TIMEOUT_MSEC, 6000])
            except Exception:
                cap = cv2.VideoCapture(src)
        else:
            cap = cv2.VideoCapture(src)
        return cap if cap.isOpened() else None

    def refresh_users(self):
        self.names = {u["id"]: u["name"] for u in db.list_users()}
        self.engine.train()

    def start_registration(self, user_id, name):
        with self.lock:
            self.reg = {"user_id": user_id, "name": name, "count": 0,
                        "target": config.SAMPLES_PER_PERSON, "last": 0.0, "done": False}

    def registration_state(self):
        with self.lock:
            return dict(self.reg) if self.reg else None

    # ---------- main loop ----------
    def _loop(self, gen):
        while self.running and gen == self._gen:
            if not self.monitoring:
                if self.cap is not None:      # free the camera while stopped
                    self.cap.release(); self.cap = None
                self.camera_ok = False
                self._publish(self._message_frame("Monitoring stopped - press Start"))
                time.sleep(0.3)
                continue
            if self._reopen:
                self._reopen = False
                if self.cap is not None:
                    self.cap.release(); self.cap = None
            if self.cap is None:
                wanted = self.source
                self.camera_ok = False
                self.status_text = "Connecting to camera source..."
                cap = self._open()
                if self.source != wanted or self._reopen:     # user changed source while connecting
                    if cap is not None:
                        cap.release()
                    continue
                self.cap = cap
                if self.cap is None:
                    self.camera_ok = False
                    self.status_text = "Camera not available"
                    self._publish(self._message_frame("Camera not available - check the source"))
                    time.sleep(2)
                    continue
            cap = self.cap
            if cap is None:
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                # video file ended -> loop it; live camera -> reconnect
                if isinstance(self.source, str) and os.path.isfile(self.source):
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                elif self.cap is not None:
                    self.cap.release(); self.cap = None
                time.sleep(0.2)
                continue
            self.camera_ok = True
            try:
                frame = self._process(frame)
            except Exception as e:  # never let the thread die
                print("Processing error:", e)
            self._publish(frame)
        if not self.running and self.cap is not None:      # loop was stopped
            self.cap.release(); self.cap = None

    def _process(self, frame):
        h, w = frame.shape[:2]
        if w != config.FRAME_WIDTH:
            frame = cv2.resize(frame, (config.FRAME_WIDTH, int(h * config.FRAME_WIDTH / w)))
        self._size = (frame.shape[1], frame.shape[0])
        self._faces = []                           # boxes for the browser overlay
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_eq = cv2.equalizeHist(gray)
        faces = self.engine.detect(gray_eq)
        clean = frame.copy()                       # un-annotated copy for evidence
        any_unknown = False
        known_names = []

        # ---- registration mode ----
        reg = self.reg
        if reg and not reg["done"]:
            if faces:
                box = max(faces, key=lambda b: b[2] * b[3])
                now = time.time()
                if now - reg["last"] > 0.25:
                    face = self.engine.preprocess(gray, box)
                    self.engine.save_sample(reg["user_id"], face, reg["count"])
                    with self.lock:
                        reg["count"] += 1
                        reg["last"] = now
                x, y, bw, bh = box
                cv2.rectangle(frame, (x, y), (x + bw, y + bh), YELLOW, 2)
                self._faces.append({"box": [x, y, bw, bh], "kind": "reg",
                                    "label": f"Registering {reg['name']} {reg['count']}/{reg['target']}"})
            cv2.putText(frame, f"Registering {reg['name']}: {reg['count']}/{reg['target']}",
                        (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, YELLOW, 2)
            if reg["count"] >= reg["target"]:
                self.refresh_users()
                with self.lock:
                    reg["done"] = True
            self.unknown_count = 0
            return frame

        # ---- normal surveillance mode ----
        for box in faces:
            face = self.engine.preprocess(gray, box)
            uid, conf = self.engine.predict(face)
            x, y, bw, bh = box
            if uid is not None and uid in self.names:
                name = self.names[uid]
                known_names.append(name)
                self._faces.append({"box": [x, y, bw, bh], "kind": "known",
                                    "label": f"{name} (Authorized)"})
                cv2.rectangle(frame, (x, y), (x + bw, y + bh), GREEN, 2)
                cv2.putText(frame, f"{name} (Authorized)", (x, y - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 2)
            else:
                any_unknown = True
                self._faces.append({"box": [x, y, bw, bh], "kind": "unknown",
                                    "label": "UNREGISTERED FACE"})
                cv2.rectangle(frame, (x, y), (x + bw, y + bh), RED, 3)
                cv2.putText(frame, "UNREGISTERED FACE", (x, y - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2)

        self.unknown_count = self.unknown_count + 1 if any_unknown else 0
        if (self.unknown_count >= config.UNKNOWN_FRAMES_TO_ALERT
                and time.time() - self.last_alert_ts > config.ALERT_COOLDOWN_SEC):
            self._raise_alert(clean, frame)

        recent = self.latest_alert and time.time() - self.latest_alert["ts"] < 5
        if recent:
            cv2.rectangle(frame, (0, 0), (frame.shape[1] - 1, frame.shape[0] - 1), RED, 8)
            cv2.putText(frame, "!! SECURITY ALERT !!", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, RED, 3)
        if any_unknown:
            self.status_text = "ALERT: Unregistered face detected"
        elif known_names:
            self.status_text = "Authorized: " + ", ".join(sorted(set(known_names)))
        elif faces:
            self.status_text = "Face detected"
        else:
            self.status_text = "Monitoring - no face"
        cv2.putText(frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        return frame

    def _raise_alert(self, evidence_frame, annotated):
        self.last_alert_ts = time.time()
        self.unknown_count = 0
        os.makedirs(config.EVIDENCE_DIR, exist_ok=True)
        fname = datetime.now().strftime("alert_%Y%m%d_%H%M%S.jpg")
        ok, buf = cv2.imencode(".jpg", annotated)
        if ok:
            buf.tofile(os.path.join(config.EVIDENCE_DIR, fname))
        alert_id = db.add_alert("Unregistered Face", fname)
        self.latest_alert = {"id": alert_id, "ts": time.time(), "image": fname,
                             "time": datetime.now().strftime("%H:%M:%S")}
        threading.Thread(target=_beep, daemon=True).start()
        print(f"[ALERT] #{alert_id} saved {fname}")

    # ---------- browser camera (used on Render / any cloud host) ----------
    def process_browser_frame(self, jpeg_bytes):
        """The browser opens the camera and uploads one small JPEG frame.
        Run the SAME detect -> recognise -> alert pipeline and return only the
        face boxes (JSON); the browser shows its own smooth video and draws the boxes."""
        frame = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return None
        with self.proc_lock:
            self.last_browser_frame = time.time()
            if not self.monitoring:
                self.camera_ok = False
                return {"stopped": True, "faces": [], "w": 640, "h": 480, "alert": False,
                        "status": self.status_text}
            self.camera_ok = True
            try:
                self._process(frame)
            except Exception as e:          # never crash the request
                print("Processing error:", e)
                self._faces = []
            la = self.latest_alert
            return {"w": self._size[0], "h": self._size[1], "faces": list(self._faces),
                    "alert": bool(la and time.time() - la["ts"] < 5),
                    "status": self.status_text}

    # ---------- output ----------
    def _message_frame(self, text):
        img = np.zeros((360, 640, 3), np.uint8)
        cv2.putText(img, text, (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        return img

    def _publish(self, frame):
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self.lock:
                self.jpeg = buf.tobytes()

    def stream(self):
        while True:
            with self.lock:
                data = self.jpeg
            if data:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            time.sleep(0.04)
