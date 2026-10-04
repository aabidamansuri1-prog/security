# CCTV-Based Unregistered Face Detection and Security Alert System

A local Python web application that watches a camera feed, recognises registered
(authorized) people, and raises an alert with a saved snapshot when an
**unregistered face** appears.

**Tech stack:** Python 3.11, Flask, OpenCV (Haar Cascade + LBPH), SQLite, HTML/CSS/JavaScript

## Features
- Live monitoring from a webcam, CCTV/IP camera (RTSP/HTTP) or video file, selectable on the dashboard (MJPEG stream in the browser)
- Face detection with Haar Cascade, face matching with LBPH
- Register and delete authorized people from the dashboard
- Red box + warning banner + alarm sound for unregistered faces
- Alert history with date, time and evidence snapshot (SQLite)

## Setup
```bash
git clone https://github.com/<your-username>/cctv-face-security.git
cd cctv-face-security
python -m pip install -r requirements.txt
python check_setup.py      # verifies libraries and the face detector
python app.py
```
Open http://127.0.0.1:5000

> Tip: keep the folder path free of spaces and outside OneDrive (for example `C:\cctv_security`).

## Live demo (Render)
**Live app:** https://YOUR-APP-NAME.onrender.com  (free tier: the first load can take about a minute)

On Render the server has no webcam, so the **visitor's browser opens the camera**. The live video is
played smoothly in the browser itself; every fraction of a second one small frame is sent to
`/api/frame`, the same detection / recognition / alert code runs on the server, and the face boxes
it returns are drawn on top of the video. Allow camera access when the browser asks.

Sources on the online version (Camera Source card):
| Option | How it works online |
|---|---|
| Webcam | Any camera on the visitor's device (0 = first, 1 = second) |
| Video file | Pick a video from your computer; it plays in the browser |
| CCTV / IP camera | Server reads the stream URL, so it must be reachable from the internet (a private `192.168.x.x` CCTV only works when the app runs on your own PC) |

Registered faces on the free tier are not permanent: they reset when the app restarts.

Render settings:
| Field | Value |
|---|---|
| Build Command | `pip install -r requirements-render.txt` |
| Start Command | `gunicorn app:app --workers 1 --threads 4 --timeout 120` |
| Environment variable | `PYTHON_VERSION` = `3.11.9` |

Running on your own PC (`python app.py`) is unchanged and still reads the webcam directly.

## Camera source (webcam, CCTV / IP camera, video file)
Use the **Camera Source** card on the dashboard - no code changes needed:

| Type | What to enter | Example |
|---|---|---|
| Webcam | camera number | `0` |
| CCTV / IP camera | RTSP or HTTP stream address | `rtsp://user:pass@192.168.1.10:554/stream` |
| Phone as IP camera | address shown by an IP-camera app | `http://192.168.1.5:8080/video` |
| Video file | full path of a recorded video | `C:\cctv_security\demo.mp4` |

Use **Start / Stop monitoring** to pause the feed. The chosen source is remembered
between runs. Network streams give up after 6 seconds if the address is wrong.
The exact RTSP address depends on the camera / NVR brand.

## Usage
1. Click **Enable alarm sound** once.
2. Enter a name and click **Start Registration**; look at the camera until the bar is full.
3. Registered people get a green box; anyone else gets a red box and triggers an alert.

## Configuration (`config.py`)
| Setting | Meaning |
|---|---|
| `CAMERA_SOURCE` | default source at first start (env var); later changed from the dashboard |
| `RECOGNITION_THRESHOLD` | Lower = stricter matching (default 70) |
| `UNKNOWN_FRAMES_TO_ALERT` | Frames with an unknown face before alerting |
| `ALERT_COOLDOWN_SEC` | Minimum gap between two alerts |

## Project structure
```
app.py            Flask routes (+ /api/frame for the browser camera)
camera.py         Capture, detect, recognise, alert loop
face_engine.py    Haar detection + LBPH recognition
database.py       SQLite (users, alerts)
templates/ static/ Dashboard
check_setup.py    Setup diagnostic
requirements.txt          Local install (Windows)
requirements-render.txt   Render install (headless OpenCV + gunicorn)
```

## Privacy and limits
Face samples and snapshots stay on your computer and are excluded from Git.
This is a classroom prototype: LBPH is sensitive to lighting and angle, so an
"unregistered" label means only "no close match found". Use only with the consent
of the people being recorded.

## Author
Aabida Siddiq Mansuri - B.Sc. Computer Science, RP Institute of Hospitality & Management
