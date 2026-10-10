import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PointerLockControls } from "three/addons/controls/PointerLockControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { GLTFExporter } from "three/addons/exporters/GLTFExporter.js";

// ---- constants (feet) ------------------------------------------------------
const WALL_H = 10, WALL_T = 0.75 /* 9" brick wall */, DOOR_H = 8, GATE_H = 7.5, EYE = 5.5;
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
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
view.appendChild(renderer.domElement);
const labelRenderer = new CSS2DRenderer();
labelRenderer.domElement.style.cssText = "position:absolute;top:0;left:0;pointer-events:none";
view.appendChild(labelRenderer.domElement);

// ---- procedural textures: drawn on canvas, so they work offline and travel inside the AR GLB ----
function canvasTex(size, draw) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  draw(c.getContext("2d"), size);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return t;
}
const rand = (a, b) => a + Math.random() * (b - a);
function speckle(g, s, n, colors, size = 2) {
  for (let i = 0; i < n; i++) {
    g.fillStyle = colors[i % colors.length];
    g.fillRect(Math.random() * s, Math.random() * s, size, size);
  }
}
function tiles(g, s, n, base, grout, jitter = 6) {
  const t = s / n;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const v = rand(-jitter, jitter);
    g.fillStyle = `rgb(${base[0] + v},${base[1] + v},${base[2] + v})`;
    g.fillRect(i * t, j * t, t, t);
  }
  g.strokeStyle = grout;
  g.lineWidth = 2;
  for (let i = 0; i <= n; i++) {
    g.beginPath(); g.moveTo(i * t, 0); g.lineTo(i * t, s); g.stroke();
    g.beginPath(); g.moveTo(0, i * t); g.lineTo(s, i * t); g.stroke();
  }
}
// each texture covers `ft` feet before repeating
const TEX = {
  wood: { ft: 6, map: canvasTex(256, (g, s) => {
    const rows = 6, h = s / rows;
    for (let r = 0; r < rows; r++) {
      let x = -rand(0, s / 2);
      while (x < s) {
        const len = rand(s * 0.4, s * 0.8), l = rand(34, 46);
        g.fillStyle = `hsl(28, 42%, ${l}%)`;
        g.fillRect(x, r * h, len, h);
        g.strokeStyle = "rgba(60,35,15,.18)";
        for (let k = 0; k < 5; k++) { g.beginPath(); g.moveTo(x, r * h + rand(2, h - 2)); g.bezierCurveTo(x + len / 3, r * h + rand(0, h), x + len * 2 / 3, r * h + rand(0, h), x + len, r * h + rand(2, h - 2)); g.stroke(); }
        g.fillStyle = "rgba(40,22,10,.55)"; g.fillRect(x, r * h, 1.5, h);
        x += len;
      }
      g.fillStyle = "rgba(40,22,10,.45)"; g.fillRect(0, r * h, s, 1.5);
    }
  }) },
  marble: { ft: 4, map: canvasTex(256, (g, s) => {
    tiles(g, s, 2, [236, 231, 222], "#cbbfae", 4);
    g.strokeStyle = "rgba(130,118,104,.22)";
    for (let k = 0; k < 14; k++) {
      g.lineWidth = rand(0.5, 2);
      g.beginPath(); g.moveTo(rand(0, s), rand(0, s));
      g.bezierCurveTo(rand(0, s), rand(0, s), rand(0, s), rand(0, s), rand(0, s), rand(0, s)); g.stroke();
    }
  }) },
  kitchen: { ft: 4, map: canvasTex(256, (g, s) => {
    const n = 4, t = s / n;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      g.fillStyle = (i + j) % 2 ? "#e8dcc4" : "#b9895f";
      g.fillRect(i * t, j * t, t, t);
    }
    speckle(g, s, 900, ["rgba(0,0,0,.05)", "rgba(255,255,255,.08)"]);
    g.strokeStyle = "#8f7a62"; g.lineWidth = 2;
    for (let i = 0; i <= n; i++) { g.beginPath(); g.moveTo(i * t, 0); g.lineTo(i * t, s); g.stroke(); g.beginPath(); g.moveTo(0, i * t); g.lineTo(s, i * t); g.stroke(); }
  }) },
  bath: { ft: 3, map: canvasTex(256, (g, s) => tiles(g, s, 8, [196, 226, 234], "#f4f8f9", 8)) },
  pavers: { ft: 6, map: canvasTex(256, (g, s) => {
    const rows = 8, h = s / rows, w = h * 2;
    for (let r = 0; r < rows; r++) for (let x = (r % 2) * -w / 2; x < s; x += w) {
      const v = rand(-10, 10);
      g.fillStyle = `rgb(${150 + v},${148 + v},${142 + v})`;
      g.fillRect(x + 1, r * h + 1, w - 2, h - 2);
    }
    speckle(g, s, 1500, ["rgba(0,0,0,.08)", "rgba(255,255,255,.08)"]);
  }) },
  grass: { ft: 8, map: canvasTex(256, (g, s) => {
    g.fillStyle = "#5f8f45"; g.fillRect(0, 0, s, s);
    speckle(g, s, 6000, ["#6fa04f", "#527d3a", "#7cad5a", "#4a7234"], 2);
  }) },
  concrete: { ft: 6, map: canvasTex(256, (g, s) => {
    g.fillStyle = "#b9b6ae"; g.fillRect(0, 0, s, s);
    speckle(g, s, 3000, ["rgba(0,0,0,.07)", "rgba(255,255,255,.1)"]);
  }) },
  plaster: { ft: 6, map: canvasTex(256, (g, s) => {
    g.fillStyle = "#f2ece2"; g.fillRect(0, 0, s, s);
    speckle(g, s, 2500, ["rgba(120,100,80,.05)", "rgba(255,255,255,.25)"], 3);
  }) },
  asphalt: { ft: 10, map: canvasTex(256, (g, s) => {
    g.fillStyle = "#3d4045"; g.fillRect(0, 0, s, s);
    speckle(g, s, 5000, ["#4a4d52", "#33363a", "#55585c"], 2);
  }) },
};
function scaleUV(geo, su, sv) {
  const uv = geo.attributes.uv;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * su, uv.getY(i) * sv);
  return geo;
}

const scene = new THREE.Scene();
scene.background = canvasTex(256, (g, s) => {
  const grd = g.createLinearGradient(0, 0, 0, s);
  grd.addColorStop(0, "#8fb8de"); grd.addColorStop(0.6, "#cfe0ee"); grd.addColorStop(1, "#eef2f0");
  g.fillStyle = grd; g.fillRect(0, 0, s, s);
});
scene.fog = new THREE.Fog(0xe4ece9, 300, 900);
const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 2000);
scene.add(new THREE.HemisphereLight(0xeaf2ff, 0x6b5f4a, 1.0));
const sun = new THREE.DirectionalLight(0xfff1dc, 2.2);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -80, right: 80, top: 80, bottom: -80, far: 400 });
scene.add(sun, sun.target);
const groundTex = TEX.grass.map.clone();
groundTex.repeat.set(2000 / 12, 2000 / 12);
groundTex.needsUpdate = true;
const ground = new THREE.Mesh(new THREE.PlaneGeometry(2000, 2000),
  new THREE.MeshStandardMaterial({ map: groundTex, color: 0xc4c9b4, roughness: 1 }));
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.05;
ground.receiveShadow = true;
scene.add(ground);

const house = new THREE.Group();   // exported to AR
const labels = new THREE.Group();  // screen-only
const site = new THREE.Group();    // street + driveway, screen-only
scene.add(house, labels, site);

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
const std = (o) => new THREE.MeshStandardMaterial({ roughness: 0.85, ...o });
const wallMat = std({ map: TEX.plaster.map, roughness: 0.95 });
const lintelMat = wallMat;
const frameMat = std({ color: 0x4a2c17, roughness: 0.6 });
const doorMat = std({ map: TEX.wood.map, color: 0xd9b48c, roughness: 0.55 });
const mainDoorMat = std({ map: TEX.wood.map, color: 0x8a5a33, roughness: 0.45 });
const steelMat = std({ color: 0x1d2024, roughness: 0.4, metalness: 0.7 });
const pillarMat = std({ color: 0xb46a4a, roughness: 0.9 });   // brick-red gate pillars
const capMat = std({ color: 0xe9e2d4, roughness: 0.7 });
const M = {
  fabric: std({ color: 0x3f5f7a, roughness: 1 }), cushion: std({ color: 0xd9c9a8, roughness: 1 }),
  sheet: std({ color: 0xf4f1ea, roughness: 1 }), quilt: std({ color: 0x9c3d3d, roughness: 1 }),
  wood: std({ map: TEX.wood.map, color: 0xa87a52, roughness: 0.6 }), counter: std({ color: 0x2f3236, roughness: 0.3 }),
  trunk: std({ color: 0x6b4a2f }), leaf: std({ color: 0x4f8a3a, flatShading: true }),
  car: std({ color: 0xb3262d, roughness: 0.25, metalness: 0.5 }), glass: std({ color: 0x223344, roughness: 0.1, metalness: 0.8 }),
  tyre: std({ color: 0x151515 }), road: std({ map: TEX.asphalt.map, roughness: 1 }),
  drive: std({ map: TEX.pavers.map, roughness: 1 }), line: std({ color: 0xf2f2f2 }),
};
// floor finish per room, the way a Pakistani house is usually finished
function floorTex(name) {
  const n = name.toLowerCase();
  if (/lawn|garden|grass|sehan|courtyard/.test(n)) return TEX.grass;
  if (/porch|garage|parking|car/.test(n)) return TEX.pavers;
  if (/bath|wash|toilet|wc/.test(n)) return TEX.bath;
  if (/kitchen/.test(n)) return TEX.kitchen;
  if (/store|laundry|pantry/.test(n)) return TEX.concrete;
  if (/drawing|lounge|tv|living|dining|hall/.test(n)) return TEX.marble;
  return TEX.wood; // bedrooms etc.
}

// ---- build the 3D house from server geometry ------------------------------
let pulse = [];
function build(bundle, changed = new Set()) {
  for (const g of [house, labels, site]) {
    g.traverse((o) => o.geometry?.dispose());
    g.clear();
  }
  pulse = [];
  const { plan, geometry } = bundle;
  for (const r of plan.rooms) {
    const tex = floorTex(r.name);
    const mat = std({ map: tex.map, roughness: tex === TEX.marble ? 0.35 : 0.9 });
    const floor = new THREE.Mesh(scaleUV(new THREE.PlaneGeometry(r.w, r.h), r.w / tex.ft, r.h / tex.ft), mat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(r.x + r.w / 2, 0.02, r.y + r.h / 2);
    floor.receiveShadow = true;
    house.add(floor);
    if (changed.has(r.name)) pulse.push(mat);
    furnish(r);

    const div = document.createElement("div");
    div.className = "label" + (changed.has(r.name) ? " changed" : "");
    div.innerHTML = `${esc(r.name)}<small>${fmt(r.w)} × ${fmt(r.h)} ft</small>`;
    const lab = new CSS2DObject(div);
    lab.position.set(r.x + r.w / 2, 1, r.y + r.h / 2);
    labels.add(lab);
  }
  for (const w of geometry.walls) addBox(w, 0, WALL_H, wallMat, WALL_T);
  const rooms = new Map(plan.rooms.map((r) => [r.name, r]));
  for (const d of geometry.doors) {
    const room = rooms.get(d.b) || rooms.get(d.a);
    const inward = sideOf(d, d.b === "outside" ? rooms.get(d.a) : room);
    if (d.kind === "gate") { addGate(d, inward); continue; }
    addBox(d, DOOR_H, WALL_H, lintelMat, WALL_T);
    addFrame(d);
    addLeaf(d, d.lo, 1, d.hi - d.lo - 0.1, DOOR_H - 0.1, d.kind === "main" ? mainDoorMat : doorMat, inward, d.kind === "main" ? 0.6 : 1.2);
    if (d.kind === "main" && d.b !== "outside") {
      const other = [d.a, d.b].find((n) => !/porch|garage|parking|car/i.test(n)) || d.b;
      tag(d, /drawing|guest/i.test(other) ? "Guest entrance" : "Family entrance", DOOR_H + 1.2, "entry");
    }
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
  if (mat === wallMat) scaleUV(geo, (len + extra) / TEX.plaster.ft, h / TEX.plaster.ft);
  const m = new THREE.Mesh(geo, mat);
  const mid = (seg.lo + seg.hi) / 2;
  if (seg.axis === "h") m.position.set(mid, y0 + h / 2, seg.c);
  else m.position.set(seg.c, y0 + h / 2, mid);
  m.castShadow = m.receiveShadow = true;
  house.add(m);
}

// a box of size (along the wall, height, across the wall) centred at distance `at` along a door's wall
function wallBox(d, at, y, len, h, t, mat, group = house) {
  const m = new THREE.Mesh(d.axis === "h" ? new THREE.BoxGeometry(len, h, t) : new THREE.BoxGeometry(t, h, len), mat);
  if (d.axis === "h") m.position.set(at, y + h / 2, d.c);
  else m.position.set(d.c, y + h / 2, at);
  m.castShadow = m.receiveShadow = true;
  group.add(m);
  return m;
}

// +1 if the room lies on the +z (h wall) or +x (v wall) side of the door's wall, else -1
function sideOf(d, room) {
  if (!room) return 1;
  const centre = d.axis === "h" ? room.y + room.h / 2 : room.x + room.w / 2;
  return centre >= d.c ? 1 : -1;
}

function addFrame(d) {
  for (const at of [d.lo + 0.12, d.hi - 0.12]) wallBox(d, at, 0, 0.25, DOOR_H, WALL_T + 0.12, frameMat);
  wallBox(d, (d.lo + d.hi) / 2, DOOR_H - 0.25, d.hi - d.lo, 0.25, WALL_T + 0.12, frameMat);
}

// a door leaf (or gate leaf `obj`) hinged at `hinge`, running along the wall in direction dir (+1/-1),
// swung open by `angle` radians towards the inward side
function addLeaf(d, hinge, dir, width, height, mat, inward, angle, obj = null) {
  const pivot = new THREE.Group();
  const leaf = obj || new THREE.Mesh(new THREE.BoxGeometry(width, height, 0.15), mat);
  if (!obj) { leaf.position.set(dir * width / 2, height / 2, 0); leaf.castShadow = true; }
  else obj.scale.x = dir;
  pivot.add(leaf);
  if (d.axis === "h") { pivot.position.set(hinge, 0, d.c); pivot.rotation.y = -angle * inward * dir; }
  else { pivot.position.set(d.c, 0, hinge); pivot.rotation.y = -Math.PI / 2 + angle * inward * dir; }
  house.add(pivot);
}

// the main gate: brick pillars with caps, two black steel leaves swung inward, a label and a driveway to the street
function addGate(d, inward) {
  const w = d.hi - d.lo, half = w / 2 - 0.15;
  for (const at of [d.lo, d.hi]) {
    wallBox(d, at, 0, 1.6, GATE_H + 1.5, 1.6, pillarMat);
    wallBox(d, at, GATE_H + 1.5, 2.0, 0.35, 2.0, capMat);
  }
  for (const [hinge, dir] of [[d.lo + 0.8, 1], [d.hi - 0.8, -1]]) {
    const g = new THREE.Group(), lw = half - 0.8;
    const bar = (x, y, bw, bh) => { const m = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, 0.12), steelMat); m.position.set(x, y, 0); m.castShadow = true; g.add(m); };
    bar(lw / 2, 0.4, lw, 0.2); bar(lw / 2, GATE_H - 0.1, lw, 0.2); bar(lw / 2, GATE_H * 0.45, lw, 0.15);
    bar(0.08, GATE_H / 2, 0.16, GATE_H); bar(lw - 0.08, GATE_H / 2, 0.16, GATE_H);
    for (let x = 0.5; x < lw - 0.3; x += 0.45) bar(x, GATE_H / 2 + 0.1, 0.06, GATE_H - 0.6);
    addLeaf(d, hinge, dir, lw, GATE_H, null, inward, 0.95, g);
  }
  tag(d, "Main gate", GATE_H + 3, "gate");
  // driveway out to a street running along this side of the plot
  const out = -inward, s = current.stats, mid = (d.lo + d.hi) / 2, len = 14, roadW = 18;
  const across = d.axis === "h" ? s.footprint_w : s.footprint_h;
  const plane = (pw, ph, along, off, mat, ft) => {
    const geo = new THREE.PlaneGeometry(pw, ph);
    if (ft) scaleUV(geo, pw / ft, ph / ft);
    const m = new THREE.Mesh(geo, mat);
    m.rotation.x = -Math.PI / 2;
    if (d.axis === "h") m.position.set(along, 0.01, d.c + out * off);
    else { m.rotation.z = Math.PI / 2; m.position.set(d.c + out * off, 0.01, along); }
    m.receiveShadow = true;
    site.add(m);
  };
  plane(w + 2, len, mid, len / 2, M.drive, TEX.pavers.ft);
  plane(across + 200, roadW, across / 2, len + roadW / 2, M.road, TEX.asphalt.ft);
  for (let a = -100; a < across + 100; a += 10) plane(4, 0.4, a, len + roadW / 2, M.line);
}

function tag(d, text, y, cls) {
  const div = document.createElement("div");
  div.className = "sign " + cls;
  div.textContent = text;
  const t = new CSS2DObject(div);
  const mid = (d.lo + d.hi) / 2;
  if (d.axis === "h") t.position.set(mid, y, d.c); else t.position.set(d.c, y, mid);
  labels.add(t);
}

// simple furniture so each room reads at a glance (and a car in the porch, trees on the lawn)
function furnish(r) {
  const n = r.name.toLowerCase(), cx = r.x + r.w / 2, cz = r.y + r.h / 2;
  const long = r.w >= r.h, L = Math.max(r.w, r.h), S = Math.min(r.w, r.h);
  const box = (w, h, dz, x, y, z, mat, rotY = 0) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, dz), mat);
    m.position.set(x, y + h / 2, z); m.rotation.y = rotY; m.castShadow = m.receiveShadow = true; house.add(m); return m;
  };
  if (/porch|garage|parking|car/.test(n) && L >= 12 && S >= 8) {
    const g = new THREE.Group(), cl = Math.min(15, L - 3), cw = Math.min(6.2, S - 2);
    const part = (w, h, dz, x, y, mat) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, dz), mat); m.position.set(x, y, 0); m.castShadow = true; g.add(m); };
    part(cl, 2.2, cw, 0, 1.7, M.car);
    part(cl * 0.5, 1.7, cw * 0.9, -cl * 0.05, 3.6, M.glass);
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
      const t = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 1.1, 0.8, 20), M.tyre);
      t.rotation.x = Math.PI / 2; t.position.set(sx * cl * 0.32, 1.1, sz * (cw / 2 - 0.3)); g.add(t);
    }
    g.position.set(cx, 0, cz);
    g.rotation.y = long ? 0 : Math.PI / 2;
    house.add(g);
  } else if (/lawn|garden|grass|sehan|courtyard/.test(n)) {
    const count = Math.max(1, Math.min(5, Math.floor((r.w * r.h) / 140)));
    for (let i = 0; i < count; i++) {
      const x = long ? r.x + r.w * (i + 0.5) / count : cx + (i % 2 ? 1 : -1) * r.w * 0.2;
      const z = long ? cz + (i % 2 ? 1 : -1) * r.h * 0.2 : r.y + r.h * (i + 0.5) / count;
      const size = Math.min(3.5, S / 3);
      box(0.6, 4, 0.6, x, 0, z, M.trunk);
      const top = new THREE.Mesh(new THREE.IcosahedronGeometry(size, 0), M.leaf);
      top.position.set(x, 4 + size * 0.8, z); top.castShadow = true; house.add(top);
    }
  } else if (/dining/.test(n) && S >= 8) {
    box(long ? 6 : 3.5, 2.5, long ? 3.5 : 6, cx, 0, cz, M.wood);
  } else {
    // pieces that stand against a wall: pick a wall with no door behind them
    const sides = { n: ["h", r.y, cx, 1], s: ["h", r.y + r.h, cx, -1], w: ["v", r.x, cz, 1], e: ["v", r.x + r.w, cz, -1] };
    const free = (k, along) => {
      const [axis, c, mid] = sides[k];
      return !current.geometry.doors.some((d) => d.axis === axis && Math.abs(d.c - c) < 0.01
        && d.lo < mid + along / 2 + 1 && d.hi > mid - along / 2 - 1);
    };
    const pick = (along, order) => order.find((k) => free(k, along));
    // box of `along` x `depth` set `inset` ft off wall k
    const against = (k, along, depth, inset, h, y, mat) => {
      const [axis, c, mid, dir] = sides[k], off = c + dir * (inset + depth / 2);
      return axis === "h" ? box(along, h, depth, mid, y, off, mat) : box(depth, h, along, off, y, mid, mat);
    };
    const longSides = long ? ["n", "s", "w", "e"] : ["w", "e", "n", "s"];
    const shortSides = long ? ["w", "e", "n", "s"] : ["n", "s", "w", "e"];
    if (/bed|master/.test(n) && S >= 8) {
      const bl = Math.min(6.5, S - 2), k = pick(5, shortSides);
      if (k) {
        against(k, 5, 0.3, 0.4, 3.5, 0, M.wood);           // headboard
        against(k, 5, bl, 0.7, 1.6, 0, M.wood);             // frame
        against(k, 4.8, bl - 0.3, 0.8, 0.5, 1.6, M.sheet);  // mattress
        against(k, 4.9, bl * 0.55, 0.7 + bl * 0.45, 0.25, 2.1, M.quilt);
      }
    } else if (/drawing|lounge|tv|living|family|hall/.test(n) && S >= 9) {
      const sl = Math.min(8, L - 4), k = pick(sl, longSides);
      if (k) {
        against(k, sl, 3, 0.5, 1.5, 0, M.fabric);
        against(k, sl, 0.8, 0.5, 1.6, 1.5, M.fabric);
        against(k, sl - 0.6, 2.2, 1.3, 0.3, 1.5, M.cushion);
        against(k, 4, 2.2, 5, 1.3, 0, M.wood);             // coffee table
      }
    } else if (/kitchen/.test(n) && S >= 7) {
      const span = (k) => (sides[k][0] === "h" ? r.w : r.h) - 2;
      const k = longSides.find((k) => free(k, span(k)));
      if (k) against(k, span(k), 2, 0.4, 3, 0, M.counter);
    }
  }
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
  else camera.position.set(cx + size * 0.55, size * 0.9, cz - size * 1.05); // from the street, gate in view
  sun.position.set(cx + 45, 100, cz - 40); // light the street side the camera looks at
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
  "make the kitchen 2 ft bigger",
  "add a 7x8 bath on the east side of Bedroom 2",
  "swap the kitchen and Bedroom 1",
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
