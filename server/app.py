"""Naqsha API + static web app.  Run:  python -m uvicorn server.app:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

import base64
import io
import json
import os
import random
import socket
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import llm, plan as P

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Naqsha")
_model = {"glb": None, "version": 0}


def _bundle(plan, log=None, merge=False, **extra):
    """Run the planner over every plan we send out. merge=True folds its notes into the
    last log stage (the edit chat shows only that one) instead of adding a stage."""
    plan, notes = P.plan_circulation(plan)
    log = list(log or [])
    if notes and merge and log:
        log[-1] = {**log[-1], "fixes": (log[-1].get("fixes") or []) + ["planner: " + n for n in notes]}
    elif notes:
        log.append({"stage": "planner laid out the doors and main gate", "fixes": notes, "errors": P.validate(plan)})
    return {"plan": plan, "geometry": P.geometry(plan), "stats": P.stats(plan), "log": log, **extra}


def _lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


@app.get("/api/info")
def info(request: Request):
    public = os.environ.get("NAQSHA_PUBLIC_URL", "").strip()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    hostname = host.split(":")[0].lower()
    https = request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
    if public:
        ar_url = f"{public.rstrip('/')}/ar.html"
    elif host and hostname not in ("localhost", "127.0.0.1", "::1", "[::1]") and https:
        ar_url = f"https://{host}/ar.html"
    else:
        ar_url = f"http://{_lan_ip()}:{request.url.port or 8000}/ar.html"
    return {"model": llm.MODEL, "ar_url": ar_url}


@app.get("/api/sample")
def sample():
    plan = json.loads((ROOT / "samples" / "ten_marla.json").read_text())
    return _bundle(plan, log=[{"stage": "loaded sample plan", "fixes": [], "errors": P.validate(plan)}])


@app.post("/api/read")
async def read(image: UploadFile = File(...)):
    b64 = base64.b64encode(await image.read()).decode()
    try:
        plan, log, errs = llm.read_sketch(b64)
    except llm.ModelError as e:
        raise HTTPException(502, str(e))
    return _bundle(plan, log=log, remaining_errors=errs)


class PlanIn(BaseModel):
    plan: dict


class EditIn(PlanIn):
    instruction: str


@app.post("/api/build")
def build(body: PlanIn):
    """Validate + repair a plan JSON (e.g. pasted or edited by hand) without the model."""
    try:
        plan, fixes = P.repair(P.normalise(body.plan))
    except P.PlanError as e:
        raise HTTPException(400, str(e))
    return _bundle(plan, log=[{"stage": "checked plan", "fixes": fixes, "errors": P.validate(plan)}])


@app.post("/api/edit")
def edit(body: EditIn):
    try:
        plan, reply, ops, log = llm.edit_plan(P.normalise(body.plan), body.instruction)
    except (llm.ModelError, P.PlanError) as e:
        raise HTTPException(422, str(e))
    return _bundle(plan, reply=reply, ops=ops, log=log, merge=True)


class OpsIn(PlanIn):
    ops: list[dict]


class GenerateIn(BaseModel):
    prompt: str
    seed: int | None = None


@app.post("/api/ops")
def manual_ops(body: OpsIn):
    """Apply edit ops (same format as plan.apply_ops) directly, without the model."""
    try:
        plan = P.normalise(body.plan)
        new, notes = P.apply_ops(plan, body.ops)
        new, fixes = P.repair(new)
    except (P.PlanError, TypeError, ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    return _bundle(new, log=[{"stage": "manual edit", "fixes": list(notes) + list(fixes), "errors": P.validate(new)}])


@app.post("/api/generate")
def generate(body: GenerateIn):
    """Text brief -> model designs the plan -> rendered as a hand-drawn sketch PNG."""
    if not body.prompt.strip():
        raise HTTPException(400, "prompt is empty")
    try:
        plan, log = llm.design_plan(body.prompt)
    except llm.ModelError as e:
        raise HTTPException(502, str(e))
    from bench.make_sketches import render  # needs repo root on sys.path (true when run from there)
    seed = body.seed if body.seed is not None else random.randrange(1 << 30)
    buf = io.BytesIO()
    render(plan, random.Random(seed)).save(buf, format="PNG")
    image = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return _bundle(plan, log=log, image=image)


@app.post("/api/model")
async def put_model(request: Request):
    _model["glb"] = await request.body()
    _model["version"] += 1
    return {"version": _model["version"]}


@app.get("/api/model/version")
def model_version():
    return {"version": _model["version"]}


@app.get("/model.glb")
def get_model():
    if not _model["glb"]:
        raise HTTPException(404, "no model yet; open the main page first")
    return Response(_model["glb"], media_type="model/gltf-binary", headers={"Cache-Control": "no-store"})


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
