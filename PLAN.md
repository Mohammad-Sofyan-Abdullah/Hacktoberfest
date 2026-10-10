# Naqsha (نقشہ): build plan

Hand-drawn floor plan photo → checked 2D plan → 3D house you can walk through → edit by typing in English / Urdu / Roman Urdu → view on a table in AR.

Event: Hacktoberfest Islamabad 2026, 10 Oct 2026, 10:00–15:00, Cowork24 I-10.
The rule that matters most: an **open-weight model must do the core work**. In Naqsha it does both AI steps (reading the sketch and turning instructions into edits). Everything runs locally through Ollama, with no closed APIs.

---

## 1. Models to download

The machine has an RTX 4080 Laptop GPU (12 GB VRAM), 32 GB RAM and Ollama 0.12.10. Every model below fits fully on the GPU. Load one at a time.

### Required

| Model (Ollama tag) | Download | Used for | License |
|---|---|---|---|
| `qwen2.5vl:7b` | ~6.0 GB | **Primary model.** Reads the sketch photo into plan JSON, runs the repair rounds, and turns Roman Urdu / English edit instructions into ops. This is the default in `server/llm.py`. | Apache-2.0 |

```powershell
ollama pull qwen2.5vl:7b
```

### Recommended backups (download now in case the venue Wi-Fi is slow later)

| Model (Ollama tag) | Download | Why | License |
|---|---|---|---|
| `qwen3-vl:8b` | ~6.1 GB | Newer Qwen vision model that is usually better at reading handwriting and written dimensions. Drop-in swap: set `NAQSHA_MODEL=qwen3-vl:8b`. Needs Ollama ≥ 0.12.7 (you have 0.12.10). | Apache-2.0 |
| `qwen2.5vl:3b` | ~3.2 GB | Fast fallback if the 7B is too slow during the live demo. Lower accuracy on messy sketches. | Qwen Research License (non-commercial; fine for a hackathon, but say so in the README) |

```powershell
ollama pull qwen3-vl:8b
ollama pull qwen2.5vl:3b
```

### Optional (only if we split the edit step onto a text-only model)

| Model (Ollama tag) | Download | Why | License |
|---|---|---|---|
| `qwen2.5:7b` | ~4.7 GB | A text-only model is faster at producing edit-op JSON. It needs a small code change: a separate `NAQSHA_EDIT_MODEL` env var in `llm.py`. Skip it unless edits feel slow. | Apache-2.0 |

### Already installed, not used
- `gpt-oss:20b` (13 GB): too large to share 12 GB VRAM with a vision model, and it can't read images.
- `llama3.2:latest` (2 GB): text only, weak at Roman Urdu.

### Verify after downloading
```powershell
ollama list
ollama run qwen2.5vl:7b "say ok"     # warms the model up, then type /bye
```

**Total download:** ~6 GB required, ~15 GB with both backups, ~20 GB with everything.

---

## 2. How the AI is used (the "important AI usage" answer for judges)

```
sketch photo ──► qwen2.5vl (vision, JSON schema forced)
                    │
                    ▼
             plan.py validate ──► errors? ──► fed back to the model (up to 2 repair rounds)
                    │                              + deterministic repair (snap edges, fix overlaps)
                    ▼
             geometry() ──► three.js 3D walkthrough ──► GLB ──► phone AR (model-viewer)

"kitchen ko 2 feet bara karo" ──► qwen2.5vl ──► ops JSON ──► apply_ops + validate ──► retry on failure
```

- Without the model there is no sketch reading and no natural-language editing, so the AI is central to the project.
- The original engineering is the **check-and-repair loop** (`server/plan.py` + `server/llm.py`). The model's output is validated against geometric rules, the errors go back to it, and anything it can't fix is repaired deterministically.

---

## 3. Remaining work, in priority order

Time is short, so a working demo comes first and polish last.

### P0: must have for submission
- [ ] Pull `qwen2.5vl:7b` and run the app end to end:
      `cd naqsha; pip install fastapi uvicorn httpx python-multipart; python -m uvicorn server.app:app --host 0.0.0.0 --port 8000`
- [ ] Add `requirements.txt` (fastapi, uvicorn, httpx, python-multipart).
- [ ] Add `LICENSE` (MIT).
- [ ] Add a `README.md` following the brief's structure: Problem, Solution, AI Component (model names + licenses from section 1), Architecture (diagram above), Setup, Demo, Team, License, Acknowledgements (Qwen, Ollama, three.js, model-viewer, FastAPI).
- [ ] Add `.gitignore` (`__pycache__/`, `*.pyc`).
- [ ] Create the public GitHub repo, push, and submit the URL.

### P1: makes the demo land
- [ ] 2–3 real hand-drawn sketch photos in `samples/` (phone photos on plain paper, dimensions written in each room).
- [ ] Test 5 Roman Urdu edits live and keep the ones that work as the chips in the UI.
- [ ] Check the AR page on a phone on the same Wi-Fi (or a hotspot).
- [ ] Screenshots / GIF in the README.

### P2: if time allows
- [ ] Small benchmark: raw model errors vs. errors after the repair loop, across the sample sketches (the log already records this per stage). One table in the README makes a strong judging point.
- [ ] Compare `qwen2.5vl:7b` against `qwen3-vl:8b` on the same sketches and keep the better one as default.

---

## 4. Demo-day risks

| Risk | Mitigation |
|---|---|
| Venue Wi-Fi too slow to pull models | Pull everything **now** (section 1). |
| three.js / model-viewer / QR libraries load from CDN | Open the app once on good internet to cache them, or vendor the files into `web/` if time allows. |
| Model is slow on first call | Warm it up before presenting (`ollama run ... "ok"`). `keep_alive` is already 30 min. |
| Model misreads a messy sketch | Keep "Load sample 10 marla" as the fallback, and present with a neat, pre-tested sketch. |
| Phone can't reach the laptop | Use a phone hotspot that both devices join. |
