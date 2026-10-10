# Member A: Model, images and demo machine

**Owner of:** anything that needs the GPU (RTX 4080 laptop). This laptop runs Ollama and the Naqsha server during the build and the final demo.

**Files you own** (others don't edit them without asking): `server/llm.py`, `bench/`, `samples/`

Timeline assumes a 14:30 code freeze and a 15:00 finish. If the organizers announce a different cutoff, shift everything accordingly.

---

## 13:15–13:30 · Unblock the team (do this first)

1. ~~Create the public GitHub repo and push~~ **Done:** https://github.com/Mohammad-Sofyan-Abdullah/Hacktoberfest (project files are at the repo root). Share the link in the team chat, and check that it opens in a private window without logging in.
2. **Start the backup model download** in a separate terminal (about 6 GB, so start it now):
   ```powershell
   ollama pull qwen3-vl:8b
   ```
3. **Make your Ollama reachable from teammates' laptops**, so B and C can run edits without a GPU:
   - Windows search → "Edit environment variables for your account" → add `OLLAMA_HOST` = `0.0.0.0`
   - Quit Ollama from the system tray and start it again
   - Allow it through the firewall on private networks if prompted
   - Share in the chat: Ollama `http://192.168.0.185:11434`, app `http://192.168.0.185:8000` (re-check your IP with `ipconfig` if you change networks)
4. Start the server, and keep it running all afternoon:
   ```powershell
   python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
   ```

**Done when:** B and C can open `http://<your-ip>:8000` from their laptops and the repo URL works without logging in.

## 13:30–14:00 · Real sketches (the demo depends on this)

1. Draw **3 sketches on plain or grid paper**: rooms as rectangles in horizontal rows, the name and size written inside each room (`Kitchen 12x10`), doors as gaps or arcs.
   - Sketch 1: a neat 10-marla house (your demo sketch)
   - Sketch 2: a 5-marla house
   - Sketch 3: deliberately messy handwriting (the stress test)
2. Photograph each one with your phone in good light, from directly above. Save them as `samples/real_01.jpg` and so on.
3. Upload each in the app and note the result: rooms found, time, any checker fixes, and whether the 3D view looks right.
4. If a real photo reads badly, tune `READ_ROWS_PROMPT` in `server/llm.py` (e.g. say "ignore pencil smudges", "sizes are written as WxH"). **Restart the server after every change**, because auto-reload is unreliable on Windows.
5. Write a ground-truth JSON for each real sketch, in the same format as `bench/sketches/00.json`, so the benchmark can score them.

**Done when:** at least one real sketch reads correctly every time. That one becomes the demo sketch; hand it to C.

## 14:00–14:20 · Model comparison (if `qwen3-vl:8b` finished downloading)

```powershell
python -m bench.run rows                                   # qwen2.5vl:7b (current)
$env:NAQSHA_MODEL="qwen3-vl:8b"; python -m bench.run rows  # backup model
```
- Each run saves `bench/sketches/results_<mode>_<model>.json`, so runs for different models do not overwrite each other.
- Also run both on your real photos: `python -m bench.run rows samples`
- Keep whichever model is more accurate as the default (`MODEL` in `server/llm.py`). It must stay at 8B or under, and it's Apache-2.0 either way.
- Send C the numbers for the README (one row per model, real photos as a separate row).

**Done when:** the default model is decided and C has the numbers.

## 14:20–14:30 · Lock down the demo machine

- Commit and push your work (see "Git" below).
- Warm the model up: upload the demo sketch once, so the first call on stage isn't slow.
- Close heavy apps; keep the laptop on the charger.
- Record a **30-second screen-capture backup** of the full flow (Win+Alt+R): upload, 3D, walk, one edit. Give it to C.
- Open the AR page on a phone once, to confirm the phone can still reach the laptop on the venue network.

## Demo role
You **drive the laptop**: upload the sketch, walk through the house, type the edits. C narrates.

## Judge questions you answer
- *Which model, what size, how is it integrated?* `qwen2.5vl:7b` (7B, Apache-2.0) via Ollama `/api/chat` with JSON-schema structured output. It's used twice: to read the sketch and to turn instructions into edits.
- *Why not let the model output coordinates?* Show the benchmark: 57% of rooms placed correctly versus 95% with our layout solver.
- *Does it run offline?* Yes. Everything is local and nothing goes to a cloud API.

## Git
```powershell
git pull --rebase
git add server/llm.py bench samples
git commit -m "feat(ai): <what changed>"
git push
```
Small commits, one change each. Pull before every push.
