"""CCTV-Based Unregistered Face Detection and Security Alert System - Flask app."""
import os
import re
import shutil
import time
from flask import (Flask, Response, jsonify, render_template, request,
                   send_from_directory)

import config
import database as db

for d in (config.DATA_DIR, config.FACES_DIR, config.EVIDENCE_DIR):
    os.makedirs(d, exist_ok=True)
db.init_db()

from camera import SecurityCamera  # noqa: E402  (after folders/DB exist)

app = Flask(__name__)

# On Render (or when BROWSER_CAMERA=1) the server has no webcam, so the visitor's
# BROWSER opens the camera and uploads frames to /api/frame.
# On your own PC (python app.py) nothing changes: the server reads the webcam directly.
BROWSER_MODE = os.environ.get("BROWSER_CAMERA") == "1" or bool(os.environ.get("RENDER"))

camera = SecurityCamera()
if not BROWSER_MODE:
    camera.start()


@app.route("/")
def index():
    return render_template("index.html", browser_mode=BROWSER_MODE)


@app.route("/api/frame", methods=["POST"])
def api_frame():
    """Receive one JPEG frame from the browser camera, return the detected face boxes (JSON)."""
    out = camera.process_browser_frame(request.get_data())
    if out is None:
        return jsonify(error="Bad image"), 400
    return jsonify(out)


@app.route("/video_feed")
def video_feed():
    return Response(camera.stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/status")
def status():
    la = camera.latest_alert
    cam_ok = camera.camera_ok
    if BROWSER_MODE and not camera.use_server_stream:   # online only while the browser sends frames
        cam_ok = cam_ok and camera.monitoring and time.time() - camera.last_browser_frame < 5
    return jsonify(camera_ok=cam_ok, status=camera.status_text,
                   users=len(db.list_users()),
                   alerts=len(db.list_alerts(10000)),
                   latest_alert=({"id": la["id"], "time": la["time"], "image": la["image"]}
                                 if la else None))


@app.route("/api/source")
def get_source():
    if BROWSER_MODE and not camera.use_server_stream:
        return jsonify(label=camera.browser_label, monitoring=camera.monitoring,
                       camera_ok=camera.camera_ok)
    return jsonify(label=camera.source_label(), monitoring=camera.monitoring,
                   camera_ok=camera.camera_ok)


@app.route("/api/source", methods=["POST"])
def set_source():
    d = request.json or {}
    kind, value = d.get("type"), str(d.get("value", "")).strip().strip('"')
    if BROWSER_MODE and kind != "url":
        return jsonify(error="Webcam and video file run in your browser on this deployment."), 400
    if kind == "webcam":
        if not value.isdigit() or int(value) > 9:
            return jsonify(error="Webcam number must be 0-9."), 400
        src = int(value)
    elif kind == "url":
        if not re.match(r"^(rtsp|rtmp|http|https)://\S+$", value, re.I):
            return jsonify(error="Enter a stream address like rtsp://user:pass@192.168.1.10:554/stream "
                                 "or http://192.168.1.5:8080/video"), 400
        src = value
    elif kind == "file":
        if not os.path.isfile(value):
            return jsonify(error="Video file not found. Give the full path, e.g. C:\\cctv_security\\demo.mp4"), 400
        src = value
    else:
        return jsonify(error="Unknown source type."), 400
    camera.set_source(src)
    camera.set_monitoring(True)
    if BROWSER_MODE:                # server reads the (public) CCTV / IP stream itself
        camera.use_server_stream = True
        camera.start()
    return jsonify(ok=True, label=camera.source_label())


@app.route("/api/source/browser", methods=["POST"])
def use_browser_source():
    """Switch back to a source that runs in the browser (webcam / video file)."""
    if not BROWSER_MODE:
        return jsonify(error="Only used on the online deployment."), 400
    label = str((request.json or {}).get("label", "Browser camera (this device)"))[:80]
    camera.use_server_stream = False
    camera.stop()
    camera.browser_label = label
    camera.set_monitoring(True)
    return jsonify(ok=True, label=label)


@app.route("/api/monitoring", methods=["POST"])
def monitoring():
    camera.set_monitoring((request.json or {}).get("on", True))
    return jsonify(ok=True, monitoring=camera.monitoring)


@app.route("/api/users")
def users():
    return jsonify(db.list_users())


@app.route("/api/register", methods=["POST"])
def register():
    name = (request.json or {}).get("name", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9 ._-]{2,40}", name):
        return jsonify(error="Enter a valid name (2-40 letters/numbers)."), 400
    if not camera.camera_ok:
        return jsonify(error="Camera is not available."), 400
    if camera.registration_state() and not camera.registration_state()["done"]:
        return jsonify(error="A registration is already running."), 400
    if db.get_user_by_name(name):
        return jsonify(error="That name is already registered."), 400
    uid = db.add_user(name)
    camera.names[uid] = name
    camera.start_registration(uid, name)
    return jsonify(ok=True, user_id=uid)


@app.route("/api/register/status")
def register_status():
    st = camera.registration_state()
    return jsonify(st or {"done": True, "count": 0, "target": 0, "idle": True})


@app.route("/api/users/<int:uid>", methods=["DELETE"])
def delete_user(uid):
    db.delete_user(uid)
    shutil.rmtree(os.path.join(config.FACES_DIR, str(uid)), ignore_errors=True)
    camera.refresh_users()
    return jsonify(ok=True)


@app.route("/api/alerts")
def alerts():
    return jsonify(db.list_alerts())


@app.route("/api/alerts", methods=["DELETE"])
def clear_alerts():
    db.clear_alerts()
    for f in os.listdir(config.EVIDENCE_DIR):
        try:
            os.remove(os.path.join(config.EVIDENCE_DIR, f))
        except OSError:
            pass
    return jsonify(ok=True)


@app.route("/evidence/<path:fname>")
def evidence(fname):
    return send_from_directory(config.EVIDENCE_DIR, fname)


if __name__ == "__main__":
    print("Open http://127.0.0.1:5000 in your browser")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
