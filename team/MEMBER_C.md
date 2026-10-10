# Member C: Edit engine, docs, submission and pitch

**Owner of:** making edits reliable, the README, the MLH submission, and the 2-minute pitch.

**Files you own** (others don't edit them without asking): `server/plan.py`, `tests/`, `README.md`

**No GPU needed.** The engine and unit tests are pure Python. For live edits you use Member A's model over Wi-Fi.

Timeline assumes a 14:30 code freeze and a 15:00 finish. If the organizers announce a different cutoff, shift everything accordingly.

---

## Setup (13:20)

```powershell
git clone <repo URL from A>
cd naqsha
pip install -r requirements.txt
python -m unittest discover -s tests -t . -v      # expect 16/16 OK
```
To try edits, open A's app in your browser: `http://<A's IP>:8000`

## 13:25–14:00 · Stress-test edits (Roman Urdu + English)

Load the sample house, then try at least **12 instructions** like the ones below, in this order. For each, record the instruction, the ops the model produced (shown in grey under its reply), whether the house looks right, and pass/fail.

| # | Try this |
|---|---|
| 1 | kitchen ko 2 feet bara karo |
| 2 | lounge ko 3 feet chhota karo |
| 3 | Bedroom 2 ke saath east side pe 7x8 ka washroom bana do |
| 4 | kitchen aur bedroom 1 ki jagah badal do |
| 5 | lawn ka naam sehan rakh do |
| 6 | store hata do (expect a clear error: there's no store in the sample) |
| 7 | drawing room se lawn tak darwaza bana do (expect a clear error: they don't share a wall) |
| 8 | make bedroom 1 16 by 18 |
| 9 | add a 10x12 bedroom to the south of the lawn |
| 10 | car porch ko 4 feet chaura karo |
| 11 | remove the door between lounge and bath 1 |
| 12 | ghar ke peeche ek 8x10 ka store bana do |

**When something fails:**
- **Wrong maths or geometry** (overlap, wrong room pushed, a hole left behind): fix it in `server/plan.py` and add a unit test in `tests/test_plan.py` that reproduces it.
- **Model misunderstood the words** (wrong op, wrong side): tell A, who owns the prompt in `server/llm.py`. Don't edit that file yourself.
- After any change to `plan.py`, run the tests, then ask A to restart their server.

Known gaps you may hit: removing a room leaves a hole, rooms spanning two rows aren't supported, and "move X next to Y" isn't an op. Don't try to build new ops now; list them as limitations instead.

**Done when:** you have about 8 instructions that work every time. Send the best 4 to B to use as the suggestion chips in the UI (`EXAMPLES` in `web/app.js`).

## 14:00–14:20 · README and submission text

1. **README** (`README.md`):
   - Fill in the Team table: names and what each person did (A: model, reading, benchmark; B: 3D, AR, visuals; C: edit engine, testing, docs).
   - Add your edit test results to "Manual test scenarios", including the failures. Being honest about what failed earns credit.
   - Add A's model comparison and real-photo numbers to the benchmark section.
   - Embed B's images near the top: `![Sketch to 3D](docs/sketch-to-3d.png)` and the edit GIF.
   - Update "Known limitations" with anything you found.
   - Check that every Mermaid diagram still matches the code and renders on GitHub.
2. **MLH submission fields** (draft now, submit once A confirms the repo is final):
   - **Title:** Naqsha: hand-drawn floor plan to a walkable 3D house
   - **Description:**
     > Families in Pakistan plan houses on paper sketches that are hard to visualise. Naqsha turns a photo of a hand-drawn floor plan into a 3D house you can walk through, edit by typing in Roman Urdu or English ("kitchen ko 2 feet bara karo"), and place on a table in AR from a phone. Qwen2.5-VL 7B (open-weight, Apache-2.0) runs locally via Ollama: it reads room names and sizes from the sketch and turns instructions into structured edit operations. Our original work is a layout solver, geometry checker and repair loop that make the small model reliable (95% of rooms placed correctly vs 57% when the model outputs coordinates itself), plus an edit engine, 3D generation and AR export. MIT licensed.
   - **GitHub link:** the repo URL. Open it in a private window to confirm it's public and the README renders.

**Done when:** the README is complete, and the submission text is ready to paste.

## 14:20–14:30 · Final checks before code freeze

- [ ] `python -m unittest discover -s tests -t .` passes
- [ ] Search the repo for secrets: `git grep -niE "api[_-]?key|secret|token|password"` should find only README text
- [ ] LICENSE present; README shows the model name, size (7B) and runtime (Ollama)
- [ ] Repo opens without logging in
- [ ] Submit on MLH (title, description, GitHub link) before the announced cutoff

## Pitch: you narrate (2 minutes), A drives, B holds the phone

1. **(15 s) Problem:** "Every house in Pakistan starts as a sketch like this." Hold up the paper. "Families can't picture it, and every change means redrawing."
2. **(30 s) Sketch to 3D:** A uploads it. "A 7-billion-parameter open model reads it locally, with no cloud. Our checker makes it buildable." A walks through the door.
3. **(25 s) Edit:** A types "kitchen ko 2 feet bara karo". "Our engine pushes the walls so nothing overlaps."
4. **(20 s) AR:** B puts the house on the judges' table.
5. **(20 s) Contribution:** show the benchmark table. "The model alone places 57% of rooms correctly. With our layout solver, 95%."
6. **(10 s) Close:** "Open source, MIT, runs on a laptop. Naqsha."

Rehearse it twice with A and B at about 14:35. If the live model is slow or fails, play A's backup video and keep talking.

## Judge questions you answer
- *What's original?* The layout solver, checker, repair, edit engine (strip insertion that keeps walls aligned) and the benchmark. Point to `server/plan.py` and the contribution table in the README.
- *How did you test it?* 16 unit tests, an 8-sketch benchmark with ground truth, real photos, and your edit test table.
- *Limitations?* Single storey, rectangular rooms in rows, synthetic benchmark sketches, cost is an estimate only.

## Git
```powershell
git pull --rebase
git add server/plan.py tests README.md
git commit -m "fix(engine): <what changed>"     # or docs: / test:
git push
```
Small commits, one change each. Pull before every push.
