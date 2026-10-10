import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PointerLockControls } from "three/addons/controls/PointerLockControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { GLTFExporter } from "three/addons/exporters/GLTFExporter.js";

// ---- constants (feet) ------------------------------------------------------
const WALL_H = 10, WALL_T = 0.75 /* 9" brick wall */, DOOR_H = 7, EYE = 5.5;
const AR_SCALE = 0.3048 / 50; // feet -> metres at 1:50, so a house fits on a table

const $ = (id) => document.getElementById(id);
let current = null;          // last bundle from the server: {plan, geometry, stats, ...}
const history = [];

// ---- three.js setup --------------------------------------------------------
const view = $("view");
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
view.appendChild(renderer.domElement);
const labelRenderer = new CSS2DRenderer();
labelRenderer.domElement.style.cssText = "position:absolute;top:0;left:0;pointer-events:none";
view.appendChild(labelRenderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xdfe7ec);
scene.fog = new THREE.Fog(0xdfe7ec, 250, 600);
const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 2000);
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a7f6a, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -80, right: 80, top: 80, bottom: -80, far: 400 });
scene.add(sun, sun.target);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(2000, 2000), new THREE.MeshStandardMaterial({ color: 0xcfd6c4 }));
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.05;
ground.receiveShadow = true;
scene.add(ground);

const house = new THREE.Group();   // exported to AR
const labels = new THREE.Group();  // screen-only
scene.add(house, labels);

const orbit = new OrbitControls(camera, renderer.domElement);
orbit.enableDamping = true;
orbit.maxPolarAngle = Math.PI / 2.05;
const walk = new PointerLockControls(camera, renderer.domElement);
const keys = {};
addEventListener("keydown", (e) => (keys[e.code] = true));
addEventListener("keyup", (e) => (keys[e.code] = false));

function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h);
  labelRenderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
addEventListener("resize", resize);
resize();

// ---- materials -------------------------------------------------------------
const wallMat = new THREE.MeshStandardMaterial({ color: 0xf1ece2, roughness: 0.9 });
const lintelMat = new THREE.MeshStandardMaterial({ color: 0xe6dfd2, roughness: 0.9 });
const mainDoorMat = new THREE.MeshStandardMaterial({ color: 0x7c4a1e, roughness: 0.6 });
function floorColor(name) {
  const n = name.toLowerCase();
  if (/lawn|garden|grass|sehan|courtyard/.test(n)) return 0x7fb069;
  if (/porch|garage|parking|car/.test(n)) return 0x9ca3af;
  if (/bath|wash|toilet|wc/.test(n)) return 0xa5d8e6;
  if (/kitchen|store|laundry|pantry/.test(n)) return 0xe9d8a6;
  if (/drawing|lounge|tv|living|dining/.test(n)) return 0xc8a27c;
  return 0xd9b99b; // bedrooms etc.
}

// ---- build the 3D house from server geometry ------------------------------
let pulse = [];
function build(bundle, changed = new Set()) {
  for (const g of [house, labels]) {
    g.traverse((o) => o.geometry?.dispose());
    g.clear();
  }
  pulse = [];
  const { plan, geometry } = bundle;
  for (const r of plan.rooms) {
    const mat = new THREE.MeshStandardMaterial({ color: floorColor(r.name), roughness: 0.95 });
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(r.w, r.h), mat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(r.x + r.w / 2, 0.02, r.y + r.h / 2);
    floor.receiveShadow = true;
    house.add(floor);
    if (changed.has(r.name)) pulse.push(mat);

    const div = document.createElement("div");
    div.className = "label" + (changed.has(r.name) ? " changed" : "");
    div.innerHTML = `${esc(r.name)}<small>${fmt(r.w)} × ${fmt(r.h)} ft</small>`;
    const lab = new CSS2DObject(div);
    lab.position.set(r.x + r.w / 2, 1, r.y + r.h / 2);
    labels.add(lab);
  }
  for (const w of geometry.walls) addBox(w, 0, WALL_H, wallMat, WALL_T);
  for (const d of geometry.doors) {
    addBox(d, DOOR_H, WALL_H, lintelMat, WALL_T);
    if (d.main) addBox(d, 0, DOOR_H, mainDoorMat, 0.25, 0.2); // main door leaf, slightly open feel
  }
  $("empty").hidden = true;
  pushAR();
}

function addBox(seg, y0, y1, mat, t, shrink = 0) {
  const len = seg.hi - seg.lo - shrink;
  const extra = mat === wallMat ? t : 0; // overlap at corners
  const h = y1 - y0;
  const geo = seg.axis === "h"
    ? new THREE.BoxGeometry(len + extra, h, t)
    : new THREE.BoxGeometry(t, h, len + extra);
  const m = new THREE.Mesh(geo, mat);
  const mid = (seg.lo + seg.hi) / 2;
  if (seg.axis === "h") m.position.set(mid, y0 + h / 2, seg.c);
  else m.position.set(seg.c, y0 + h / 2, mid);
  m.castShadow = m.receiveShadow = true;
  house.add(m);
}

function bounds() {
  const s = current.stats;
  return { cx: s.footprint_w / 2, cz: s.footprint_h / 2, size: Math.max(s.footprint_w, s.footprint_h) };
}
function frame(top = false) {
  if (!current) return;
  const { cx, cz, size } = bounds();
  orbit.target.set(cx, 0, cz);
  if (top) camera.position.set(cx, size * 1.6, cz + 0.01);
  else camera.position.set(cx + size * 0.55, size * 0.9, cz + size * 1.05);
  sun.position.set(cx + 40, 90, cz + 30);
  sun.target.position.set(cx, 0, cz);
  orbit.update();
}

// ---- walk mode --------------------------------------------------------------
function startWalk() {
  if (!current) return;
  const main = current.geometry.doors.find((d) => d.main) || current.geometry.doors[0];
  const { cx, cz } = bounds();
  if (main) {
    const mid = (main.lo + main.hi) / 2;
    const p = main.axis === "h" ? new THREE.Vector3(mid, EYE, main.c) : new THREE.Vector3(main.c, EYE, mid);
    const out = new THREE.Vector3(p.x - cx, 0, p.z - cz).normalize().multiplyScalar(6);
    camera.position.copy(p).add(out);
    camera.lookAt(p.x, EYE, p.z);
  } else camera.position.set(cx, EYE, cz);
  orbit.enabled = false;
  walk.lock();
}
walk.addEventListener("unlock", () => { orbit.enabled = true; setMode("orbit"); frame(); });
function setMode(m) {
  $("orbitBtn").classList.toggle("active", m === "orbit");
  $("walkBtn").classList.toggle("active", m === "walk");
}
$("orbitBtn").onclick = () => { setMode("orbit"); frame(); };
$("walkBtn").onclick = () => { setMode("walk"); startWalk(); };
$("topBtn").onclick = () => { setMode("orbit"); frame(true); };

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1);
  if (walk.isLocked) {
    const sp = (keys.ShiftLeft ? 22 : 11) * dt;
    if (keys.KeyW || keys.ArrowUp) walk.moveForward(sp);
    if (keys.KeyS || keys.ArrowDown) walk.moveForward(-sp);
    if (keys.KeyA || keys.ArrowLeft) walk.moveRight(-sp);
    if (keys.KeyD || keys.ArrowRight) walk.moveRight(sp);
    camera.position.y = EYE;
  } else orbit.update();
  const glow = (Math.sin(performance.now() / 180) + 1) / 2;
  for (const m of pulse) m.emissive.setRGB(0.55 * glow, 0.4 * glow, 0);
  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
});

// ---- AR export: GLB at 1:50 sent to the server for the phone page -----------
const exporter = new GLTFExporter();
let arTimer;
function pushAR() {
  clearTimeout(arTimer);
  arTimer = setTimeout(() => {
    const { cx, cz } = bounds();
    const g = house.clone(true);
    g.position.set(-cx * AR_SCALE, 0, -cz * AR_SCALE);
    g.scale.setScalar(AR_SCALE);
    const root = new THREE.Group();
    root.add(g);
    exporter.parse(root, (glb) => fetch("/api/model", { method: "POST", body: glb }),
      (e) => console.error("GLB export failed", e), { binary: true });
  }, 300);
}

// ---- UI ----------------------------------------------------------------------
function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function fmt(n) { return Number(n.toFixed(1)).toString(); }
function pkr(n) {
  if (n >= 1e7) return `PKR ${(n / 1e7).toFixed(2)} crore`;
  if (n >= 1e5) return `PKR ${(n / 1e5).toFixed(1)} lakh`;
  return `PKR ${Math.round(n).toLocaleString()}`;
}

function busy(text) {
  $("busy").hidden = !text;
  $("busyText").textContent = text || "";
  for (const id of ["send", "sample", "rebuild"]) $(id).disabled = !!text;
}

function renderStats() {
  if (!current) return;
  const s = current.stats, per = +$("marla").value || 225, rate = +$("rate").value || 0;
  const rows = [
    ["Footprint", `${fmt(s.footprint_w)} × ${fmt(s.footprint_h)} ft`],
    ["Covered area", `${s.covered_sqft.toLocaleString()} sq ft`],
    ["Plot size", `${(s.footprint_sqft / per).toFixed(1)} marla`],
    ["Rooms", s.rooms],
    ["Rough cost", rate ? pkr(s.covered_sqft * rate) : "set a rate"],
  ];
  $("stats").innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
}
$("marla").oninput = $("rate").oninput = renderStats;

function renderLog(log, remaining) {
  const items = (log || []).map((s) => {
    const errs = s.errors || [];
    const cls = errs.length || s.problem ? "bad" : (s.fixes?.length ? "fix" : "ok");
    const bits = [];
    if (s.rooms != null) bits.push(`${s.rooms} rooms`);
    if (s.raw_errors != null) bits.push(`${s.raw_errors} problem(s) in raw output`);
    if (s.secs != null) bits.push(`${s.secs}s`);
    const detail = [...(s.fixes || []).map((f) => "fixed: " + f), ...errs.map((e) => "still wrong: " + e.msg)];
    return `<li class="${cls}"><b>${esc(s.stage)}</b><small>${esc(bits.join(" · "))}</small>${detail.map((d) => `<small>${esc(d)}</small>`).join("")}</li>`;
  });
  const ok = !(remaining && remaining.length);
  items.push(`<li class="${ok ? "ok" : "bad"}"><b>${ok ? "✓ Checker: plan is buildable" : "⚠ Checker: " + remaining.length + " problem(s) left"}</b></li>`);
  $("log").innerHTML = items.join("");
}

function apply(bundle, { changed, keepHistory = true, reframe = false } = {}) {
  if (keepHistory && current) history.push(current);
  $("undo").disabled = !history.length;
  const first = !current;
  current = bundle;
  build(bundle, changed);
  renderStats();
  $("json").value = JSON.stringify(bundle.plan, null, 2);
  if (first || reframe) frame();
}

function diff(oldPlan, newPlan) {
  const before = new Map((oldPlan?.rooms || []).map((r) => [r.name, `${r.x},${r.y},${r.w},${r.h}`]));
  return new Set(newPlan.rooms.filter((r) => before.get(r.name) !== `${r.x},${r.y},${r.w},${r.h}`).map((r) => r.name));
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

$("sample").onclick = async () => {
  busy("Loading sample…");
  try {
    const b = await api("/api/sample");
    $("thumb").hidden = true;
    renderLog(b.log, []);
    apply(b, { reframe: true });
  } catch (e) { alert(e.message); } finally { busy(); }
};

$("file").onchange = async (ev) => {
  const f = ev.target.files[0];
  if (!f) return;
  const img = await shrink(f, 1280);
  $("thumb").src = URL.createObjectURL(img);
  $("thumb").hidden = false;
  busy(`Reading sketch with ${model}…`);
  try {
    const fd = new FormData();
    fd.append("image", img, "sketch.jpg");
    const b = await api("/api/read", { method: "POST", body: fd });
    renderLog(b.log, b.remaining_errors);
    apply(b, { reframe: true });
  } catch (e) {
    $("log").innerHTML = `<li class="bad"><b>Could not read sketch</b><small>${esc(e.message)}</small></li>`;
  } finally { busy(); ev.target.value = ""; }
};

async function shrink(file, max) {
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * k);
  c.height = Math.round(bmp.height * k);
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  return new Promise((r) => c.toBlob(r, "image/jpeg", 0.9));
}

function say(cls, html) {
  const d = document.createElement("div");
  d.className = "msg " + cls;
  d.innerHTML = html;
  $("chat").appendChild(d);
  $("chat").scrollTop = 1e9;
}

$("editForm").onsubmit = async (ev) => {
  ev.preventDefault();
  const instruction = $("instr").value.trim();
  if (!instruction || !current) return;
  say("user", esc(instruction));
  $("instr").value = "";
  busy("Editing the house…");
  try {
    const b = await api("/api/edit", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: current.plan, instruction }),
    });
    const last = b.log[b.log.length - 1];
    const notes = (last.notes || []).concat(last.fixes || []);
    const retried = b.log.length > 1 ? `<code>checker rejected the first attempt (${esc(b.log[0].problem)}); model retried</code>` : "";
    say("bot", `${esc(b.reply)}<code>${esc(notes.join("\n"))}</code>${retried}`);
    apply(b, { changed: diff(current.plan, b.plan) });
  } catch (e) {
    say("bot err", esc(e.message));
  } finally { busy(); }
};

const EXAMPLES = [
  "kitchen ko 2 feet bara karo",
  "Bedroom 2 ke saath east side pe 7x8 ka washroom bana do",
  "kitchen aur bedroom 1 ki jagah badal do",
  "make the lounge 3 ft longer on the south side",
];
$("chips").innerHTML = EXAMPLES.map((t) => `<button class="chip" type="button">${esc(t)}</button>`).join("");
$("chips").onclick = (e) => { if (e.target.classList.contains("chip")) { $("instr").value = e.target.textContent; $("instr").focus(); } };

$("undo").onclick = () => {
  const prev = history.pop();
  if (prev) apply(prev, { keepHistory: false });
  $("undo").disabled = !history.length;
};

$("rebuild").onclick = async () => {
  busy("Checking plan…");
  try {
    const b = await api("/api/build", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: JSON.parse($("json").value) }),
    });
    renderLog(b.log, b.log[0].errors);
    apply(b, { changed: diff(current?.plan, b.plan), reframe: true });
  } catch (e) { alert(e.message); } finally { busy(); }
};

let model = "the model";
api("/api/info").then((i) => {
  model = i.model;
  $("foot").textContent = `Model: ${i.model} (open-weight, local via Ollama)`;
  $("arLink").href = i.ar_url;
  new QRCode($("qr"), { text: i.ar_url, width: 240, height: 240 });
}).catch(() => {});
