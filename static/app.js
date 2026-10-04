let audioCtx = null, lastAlertId = null, firstLoad = true, soundOn = false;
const $ = id => document.getElementById(id);

function enableSound() {
  audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
  soundOn = true; beep();
  $('soundBtn').textContent = '🔊 Alarm sound enabled';
}
function beep() {
  if (!audioCtx) return;
  for (let i = 0; i < 4; i++) {
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.type = 'square'; o.frequency.value = i % 2 ? 900 : 1400;
    g.gain.value = 0.15; o.connect(g); g.connect(audioCtx.destination);
    o.start(audioCtx.currentTime + i * 0.25); o.stop(audioCtx.currentTime + i * 0.25 + 0.2);
  }
}
function dismissBanner() { $('alertBanner').classList.add('hidden'); }

async function pollStatus() {
  try {
    const s = await (await fetch('/api/status')).json();
    const b = $('camBadge');
    b.textContent = 'Camera: ' + (s.camera_ok ? 'Online' : 'Offline');
    b.className = 'badge ' + (s.camera_ok ? 'ok' : 'bad');
    const st = $('statusLine');
    st.textContent = 'Status: ' + s.status;
    st.className = 'status ' + (s.status.startsWith('ALERT') ? 'alert' : 'ok');
    $('statUsers').textContent = s.users; $('statAlerts').textContent = s.alerts;
    if (s.latest_alert) {
      if (!firstLoad && s.latest_alert.id !== lastAlertId) {
        $('alertTime').textContent = s.latest_alert.time;
        $('alertBanner').classList.remove('hidden');
        if (soundOn) beep();
        loadAlerts();
      }
      lastAlertId = s.latest_alert.id;
    }
    firstLoad = false;
  } catch (e) { $('camBadge').textContent = 'Server offline'; $('camBadge').className = 'badge bad'; }
}

function esc(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function zoom(src) { $('lightImg').src = src; $('lightbox').classList.remove('hidden'); }

async function loadUsers() {
  const u = await (await fetch('/api/users')).json();
  $('usersBody').innerHTML = u.length ? u.map(x =>
    `<tr><td>${x.id}</td><td>${esc(x.name)}</td><td>${x.created_at}</td>
     <td><button class="danger small" onclick="delUser(${x.id})">Delete</button></td></tr>`).join('')
    : '<tr><td colspan="4">No registered users yet</td></tr>';
}
async function loadAlerts() {
  const a = await (await fetch('/api/alerts')).json();
  $('alertsBody').innerHTML = a.length ? a.map(x =>
    `<tr><td>${x.id}</td><td>${esc(x.alert_type)}</td><td>${x.date}</td><td>${x.time}</td>
     <td><img src="/evidence/${x.image_path}" onclick="zoom('/evidence/${x.image_path}')"></td></tr>`).join('')
    : '<tr><td colspan="5">No alerts recorded</td></tr>';
}

async function startRegister() {
  const name = $('nameInput').value.trim();
  const r = await fetch('/api/register', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                          body: JSON.stringify({name})});
  const d = await r.json();
  if (!r.ok) { $('regMsg').textContent = d.error; return; }
  $('regBtn').disabled = true; $('regMsg').textContent = 'Capturing... look at the camera.';
  loadUsers();
  const t = setInterval(async () => {
    const s = await (await fetch('/api/register/status')).json();
    $('regBar').style.width = (s.target ? 100 * s.count / s.target : 0) + '%';
    if (s.done) {
      clearInterval(t); $('regBtn').disabled = false; $('nameInput').value = '';
      $('regMsg').textContent = '✔ Registration complete.';
      loadUsers();
    }
  }, 300);
}
async function delUser(id) {
  if (!confirm('Delete this user?')) return;
  await fetch('/api/users/' + id, {method: 'DELETE'}); loadUsers();
}
async function clearAlerts() {
  if (!confirm('Delete all alert history and evidence images?')) return;
  await fetch('/api/alerts', {method: 'DELETE'}); loadAlerts();
}

const SRC_HINTS = {
  webcam: ['0', 'Webcam number: 0 = built-in, 1 = external.'],
  url: ['rtsp://user:password@192.168.1.10:554/stream', 'CCTV/NVR: rtsp://user:pass@IP:554/stream  |  Phone IP-camera app: http://IP:8080/video'],
  file: ['C:\\cctv_security\\demo.mp4', 'Full path of a recorded CCTV-style video (it loops).']
};
const SRC_HINTS_ONLINE = {
  webcam: ['0', 'Camera number on THIS device: 0 = first camera, 1 = second camera.'],
  url: ['http://PUBLIC-IP:8080/video', 'Online version: only works for a stream reachable from the internet (not 192.168.x.x). A private CCTV needs the app running on your own PC.'],
  file: ['', 'Pick a video from your computer. It plays in your browser and loops.']
};
function srcTypeChanged() {
  const t = $('srcType').value;
  const hints = window.BROWSER_MODE ? SRC_HINTS_ONLINE : SRC_HINTS;
  $('srcValue').value = hints[t][0]; $('srcHint').textContent = hints[t][1];
  if (window.BROWSER_MODE) {
    $('srcValue').style.display = t === 'file' ? 'none' : '';
    $('srcFile').style.display = t === 'file' ? '' : 'none';
  }
}
async function applyOnlineSource() {
  const t = $('srcType').value, msg = $('srcMsg');
  msg.textContent = '';
  if (t === 'url') {
    const r = await fetch('/api/source', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({type: 'url', value: $('srcValue').value})});
    const d = await r.json();
    if (!r.ok) { msg.textContent = d.error; return; }
    lastBrowserSource = null; showServerStream();
    msg.textContent = 'Source changed to: ' + d.label;
  } else {
    let arg, label;
    if (t === 'file') {
      arg = $('srcFile').files[0];
      if (!arg) { msg.textContent = 'Choose a video file first.'; return; }
      label = 'Video file: ' + arg.name;
    } else {
      arg = $('srcValue').value.trim() || '0'; label = 'Webcam ' + arg + ' (this device)';
    }
    await fetch('/api/source/browser', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({label})});
    showBrowserStage();
    if (await openBrowserSource(t, arg)) msg.textContent = 'Source changed to: ' + label;
  }
  loadSource();
}
async function applySource() {
  if (window.BROWSER_MODE) return applyOnlineSource();
  const r = await fetch('/api/source', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type: $('srcType').value, value: $('srcValue').value})});
  const d = await r.json();
  $('srcMsg').textContent = r.ok ? 'Source changed to: ' + d.label : d.error;
  loadSource();
}
async function setMonitoring(on) {
  await fetch('/api/monitoring', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({on})});
  if (window.BROWSER_MODE && lastBrowserSource) {      // (server CCTV stream is paused by the server itself)
    if (on) openBrowserSource(lastBrowserSource.kind, lastBrowserSource.arg);
    else stopBrowserCamera();
  }
  loadSource();
}

// ---------- Browser camera mode (used when hosted on Render) ----------
// The video you see is played LOCALLY by the browser (smooth). Every ~0.3 s one small frame is sent
// to the server; the server answers with face boxes, which are drawn on top of the video.
let camStream = null, camRunning = false, lastBrowserSource = null;
const camVideo = $('liveVideo'), overlay = $('overlay');
const camCanvas = document.createElement('canvas');
const KIND_COLOR = {known: '#00c800', unknown: '#ff3030', reg: '#ffd700'};

function showBrowserStage() {
  $('feed').removeAttribute('src'); $('feed').classList.add('hidden');   // closes any server stream
  $('stage').classList.remove('hidden');
}
function showServerStream() {
  stopBrowserCamera();
  $('stage').classList.add('hidden');
  $('feed').classList.remove('hidden'); $('feed').src = '/video_feed?t=' + Date.now();
}
function clearOverlay() { const c = overlay.getContext('2d'); c.clearRect(0, 0, overlay.width, overlay.height); }

// kind: 'webcam' (arg = camera number) or 'file' (arg = File chosen by the user)
async function openBrowserSource(kind, arg) {
  stopBrowserCamera();
  lastBrowserSource = {kind, arg};
  try {
    if (kind === 'file') {
      camVideo.srcObject = null; camVideo.loop = true;
      camVideo.src = URL.createObjectURL(arg);
    } else {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        $('srcMsg').textContent = 'Camera needs a secure (https) page.'; return false;
      }
      let stream = await navigator.mediaDevices.getUserMedia({video: {width: 640, height: 480}, audio: false});
      const idx = parseInt(arg || '0', 10) || 0;
      if (idx > 0) {
        const cams = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput');
        if (cams[idx]) {
          stream.getTracks().forEach(t => t.stop());
          stream = await navigator.mediaDevices.getUserMedia(
            {video: {deviceId: {exact: cams[idx].deviceId}, width: 640, height: 480}, audio: false});
        } else {
          $('srcMsg').textContent = 'Only ' + cams.length + ' camera(s) found - using camera 0.';
        }
      }
      camStream = stream;
      camVideo.removeAttribute('src'); camVideo.loop = false; camVideo.srcObject = stream;
    }
    await camVideo.play();
  } catch (e) {
    $('srcMsg').textContent = 'Could not start (' + e.name + '). Allow camera access, then press Start monitoring.';
    return false;
  }
  camRunning = true;
  browserLoop();
  return true;
}
function stopBrowserCamera() {
  camRunning = false;
  if (camStream) { camStream.getTracks().forEach(t => t.stop()); camStream = null; }
  if (camVideo) camVideo.pause();
  if (overlay) clearOverlay();
}
function drawOverlay(d) {
  overlay.width = d.w; overlay.height = d.h;
  const c = overlay.getContext('2d');
  c.clearRect(0, 0, d.w, d.h);
  c.lineWidth = 3; c.font = '16px Arial';
  (d.faces || []).forEach(f => {
    const [x, y, w, h] = f.box, col = KIND_COLOR[f.kind] || '#fff';
    c.strokeStyle = col; c.fillStyle = col;
    c.strokeRect(x, y, w, h);
    c.fillText(f.label, x, Math.max(16, y - 8));
  });
  if (d.alert) {
    c.strokeStyle = '#ff3030'; c.lineWidth = 8; c.strokeRect(0, 0, d.w, d.h);
    c.fillStyle = '#ff3030'; c.font = 'bold 22px Arial'; c.fillText('!! SECURITY ALERT !!', 12, 32);
  }
  c.fillStyle = '#fff'; c.font = '13px Arial';
  c.fillText(new Date().toLocaleString(), 10, d.h - 10);
}
async function browserLoop() {
  const ctx = camCanvas.getContext('2d');
  while (camRunning) {
    const t0 = performance.now();
    if (camVideo.videoWidth) {
      const w = 640, h = Math.round(w * camVideo.videoHeight / camVideo.videoWidth);
      camCanvas.width = w; camCanvas.height = h;
      ctx.drawImage(camVideo, 0, 0, w, h);
      const blob = await new Promise(r => camCanvas.toBlob(r, 'image/jpeg', 0.6));
      try {
        const res = await fetch('/api/frame', {method: 'POST', headers: {'Content-Type': 'image/jpeg'}, body: blob});
        if (res.ok && camRunning) drawOverlay(await res.json());
      } catch (e) { await new Promise(r => setTimeout(r, 1000)); }
    }
    const wait = 100 - (performance.now() - t0);      // next frame as soon as the server answered
    if (wait > 0) await new Promise(r => setTimeout(r, wait));
  }
}

async function loadSource() {
  const d = await (await fetch('/api/source')).json();
  $('srcLabel').textContent = d.label + (d.monitoring ? '' : '  (stopped)');
}

if (window.BROWSER_MODE) {
  srcTypeChanged();
  openBrowserSource('webcam', '0');
}
loadSource(); loadUsers(); loadAlerts(); pollStatus(); setInterval(pollStatus, 1500);
