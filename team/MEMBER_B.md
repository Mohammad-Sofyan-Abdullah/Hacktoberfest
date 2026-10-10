# Member B: 3D viewer, AR and visuals

**Owner of:** everything the user sees: the 3D house, walk mode, the AR page on the phone, and the screenshots and GIF for the README.

**Files you own** (others don't edit them without asking): `web/` (`index.html`, `style.css`, `app.js`, `ar.html`)

**No GPU needed.** You use Member A's laptop for anything involving the model.

Timeline assumes a 14:30 code freeze and a 15:00 finish. If the organizers announce a different cutoff, shift everything accordingly.

---

## Setup (13:20)

```powershell
git clone <repo URL from A>
cd naqsha
pip install -r requirements.txt
$env:OLLAMA_URL="http://<A's IP>:11434"     # use A's GPU for model calls
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000 and click **Load sample 10 marla** (this works without the model). Edits and uploads go to A's Ollama. If they fail, check that A has finished their step 3 (`OLLAMA_HOST=0.0.0.0`).

Web files are static. After editing them, just refresh the browser with Ctrl+F5; no server restart is needed.

## 13:25–13:50 · AR on a real phone (highest priority, not tested yet)

1. Join the phone to the same Wi-Fi as the laptop (or use a phone hotspot that both join).
2. In the app, load the sample, then scan the QR code in panel 4 with the phone.
3. Tap **View on your table**.
   - **Android:** this should open Google Scene Viewer.
   - **iPhone:** this should open AR Quick Look.
4. If AR doesn't start (likely because the page is plain HTTP, not HTTPS), use a tunnel:
   ```powershell
   winget install --id Cloudflare.cloudflared
   cloudflared tunnel --url http://localhost:8000
   ```
   Open the `https://….trycloudflare.com/ar.html` URL it prints on the phone. If that works, add a small "AR link" input in `web/index.html` so the QR code can point at the tunnel URL instead of the LAN IP.
5. Check the model's scale on a real table. It's 1:50 (`AR_SCALE` in `web/app.js`). If it's too small or too big, adjust it.
6. Make an edit on the laptop and confirm the phone updates within about 2 seconds.

**Done when:** you can put the house on a table from a phone, reliably, and you know which method (LAN or tunnel) to use during the demo. Tell A and C.

## 13:50–14:10 · Make the demo safe offline

Three.js, model-viewer and the QR library currently load from CDNs. If venue Wi-Fi drops, the app goes blank.
1. Download them into `web/vendor/`:
   - `https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js`
   - the addons the app uses from `https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/`: `controls/OrbitControls.js`, `controls/PointerLockControls.js`, `renderers/CSS2DRenderer.js`, `exporters/GLTFExporter.js`, plus any files they import (check the browser console for 404s)
   - `https://cdn.jsdelivr.net/npm/@google/model-viewer@3.5.0/dist/model-viewer.min.js`
   - `https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js`
2. Point the importmap in `index.html` at `vendor/three/...`, and update the script tags in `index.html` and `ar.html`.
3. Test with Wi-Fi turned off: load the sample, orbit, walk, and confirm the QR code still renders.
4. Add a line to the README Acknowledgements saying the libraries are vendored, with their licenses (MIT, Apache-2.0). Coordinate with C, who owns the README.

**Done when:** the app works with the internet unplugged.

## 14:10–14:25 · Screenshots and GIF for the README

Capture these from A's laptop or your own, at a 1440×900 window:
1. `docs/sketch-to-3d.png`: the sketch thumbnail plus the 3D house, with the checker log visible
2. `docs/edit.gif`: typing "kitchen ko 2 feet bara karo" and the house updating. Use ScreenToGif (free), keep it under 10 seconds and 5 MB.
3. `docs/walk.png`: walk mode inside the lounge
4. `docs/ar.jpg`: a phone photo of the house on a real table (**the most important image**)

Commit them under `docs/` and tell C the file names so they can embed them.

## If there's time (only after everything above works)
- Simple wall collision in walk mode (stop movement when the camera gets within about 0.5 ft of a wall)
- A "Reset camera" button
- Bigger tap targets on mobile

Don't start any of these after 14:20.

## Demo role
You **hold the phone** for the AR moment. When A says "and on your table…", place the house on the judges' table and hand them the phone.

## Judge questions you answer
- *How does 2D become 3D?* The server merges room edges into continuous walls and cuts door openings. The browser raises each wall as a 10 ft box with 9-inch thickness, adds lintels over doors, and exports a GLB at 1:50 for the phone.
- *Does AR need an app?* No. It uses `<model-viewer>` in the browser, which hands off to Scene Viewer on Android or Quick Look on iOS.

## Git
```powershell
git pull --rebase
git add web docs
git commit -m "feat(web): <what changed>"
git push
```
Small commits, one change each. Pull before every push.
