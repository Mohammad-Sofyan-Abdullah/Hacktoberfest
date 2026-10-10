"""Naqsha API + static web app.  Run:  python -m uvicorn server.app:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

import base64
import json
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


def _bundle(plan, **extra):
    return {"plan": plan, "geometry": P.geometry(plan), "stats": P.stats(plan), **extra}


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
    port = request.url.port or 8000
    return {"model": llm.MODEL, "ar_url": f"http://{_lan_ip()}:{port}/ar.html"}


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
    return _bundle(plan, reply=reply, ops=ops, log=log)


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
