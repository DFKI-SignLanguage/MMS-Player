// Render screenshots of the real-time character (GLB) together with the "signing space" box framed by the
// Top/Left/Right views of the WebGUI 3D preview: a front view, a side view, and a 45-degree view, plus a combined image.
//
// The signing space is computed with the very same function used by the WebGUI (computeSigningSpace() in
// WebGUI/static/viewer3d.js), and the scene uses the Three.js version vendored in the WebGUI.
// No server is needed: the files are served from disk to a headless browser.
//
// Usage (from this folder):
//   npm install && npx playwright install chromium
//   node render.mjs [--out DIR] [--glb FILE]
//
// Defaults: --out Docs/Pics/signing-space, --glb assets/gloria-260813.glb (both relative to the MMS-Player folder).

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { chromium } from "playwright";

const PLAYER_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const STATIC_DIR = path.join(PLAYER_DIR, "WebGUI", "static");
const ORIGIN = "http://mms-player.local";

const VIEW_W = 600, VIEW_H = 800, SCALE = 2;
const ELEVATION = 20 * Math.PI / 180;
const VIEWS = [
  { file: "front", label: "Front", dir: [0, 0, 1] },
  { file: "side", label: "Side (her left)", dir: [1, 0, 0] },
  {
    file: "45deg", label: "45 deg (front-left, 20 deg above)",
    dir: [Math.sin(Math.PI / 4) * Math.cos(ELEVATION), Math.sin(ELEVATION), Math.cos(Math.PI / 4) * Math.cos(ELEVATION)],
  },
];

function parseArgs(argv) {
  const args = { out: path.join(PLAYER_DIR, "Docs", "Pics", "signing-space"), glb: path.join(PLAYER_DIR, "assets", "gloria-260813.glb") };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--out") args.out = path.resolve(argv[++i]);
    else if (argv[i] === "--glb") args.glb = path.resolve(argv[++i]);
    else throw new Error(`Unknown argument '${argv[i]}'. Usage: node render.mjs [--out DIR] [--glb FILE]`);
  }
  return args;
}

function signingSpaceFunction() {
  const src = fs.readFileSync(path.join(STATIC_DIR, "viewer3d.js"), "utf8");
  const m = src.match(/function computeSigningSpace[\s\S]*?\n}\n/);
  if (!m) throw new Error("computeSigningSpace() not found in WebGUI/static/viewer3d.js");
  return m[0];
}

function scenePage() {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
  html, body { margin: 0; background: #fff; font: 14px -apple-system, "Segoe UI", sans-serif; }
  #c { position: relative; width: ${VIEW_W}px; height: ${VIEW_H}px; background: linear-gradient(#3a3f47, #6b717b); }
  #c canvas { display: block; }
  #lab { position: absolute; left: 12px; top: 10px; color: #fff; font-weight: 600; font-size: 18px; text-shadow: 0 1px 3px #000; }
  #dims { position: absolute; left: 12px; bottom: 10px; color: #ffe7a3; font-size: 13px; text-shadow: 0 1px 3px #000; white-space: pre; }
</style>
<script type="importmap">{"imports": {"three": "/static/vendor/three/three.module.min.js", "three/addons/": "/static/vendor/three/addons/"}}</script>
</head><body><div id="c"><div id="lab"></div><div id="dims"></div></div>
<script type="module">
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

${signingSpaceFunction()}

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(${SCALE});
renderer.setSize(${VIEW_W}, ${VIEW_H});
renderer.toneMapping = THREE.NeutralToneMapping;
document.getElementById("c").prepend(renderer.domElement);

// Same lights and floor of the WebGUI viewer
const scene = new THREE.Scene();
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8070, 1.6));
const key = new THREE.DirectionalLight(0xffffff, 1.8); key.position.set(80, 250, 250); scene.add(key);
const back = new THREE.DirectionalLight(0xffffff, 0.8); back.position.set(-150, 200, -200); scene.add(back);
const grid = new THREE.GridHelper(300, 30, 0x888888, 0xbbbbbb);
grid.material.transparent = true; grid.material.opacity = 0.35; scene.add(grid);
const camera = new THREE.PerspectiveCamera(30, ${VIEW_W} / ${VIEW_H}, 1, 5000);

const gltf = await new GLTFLoader().loadAsync("/character.glb");
scene.add(gltf.scene);
gltf.scene.updateMatrixWorld(true);
const bbox = new THREE.Box3();
gltf.scene.traverse((o) => { if (o.isSkinnedMesh || o.isMesh) bbox.expandByObject(o); });
const space = computeSigningSpace(gltf.scene, bbox);

// Translucent volume and edges of the signing space
const size = space.getSize(new THREE.Vector3()), center = space.getCenter(new THREE.Vector3());
const vol = new THREE.Mesh(new THREE.BoxGeometry(size.x, size.y, size.z),
  new THREE.MeshBasicMaterial({ color: 0xffb020, transparent: true, opacity: 0.18, depthWrite: false }));
vol.position.copy(center);
scene.add(vol);
const edges = new THREE.LineSegments(new THREE.EdgesGeometry(vol.geometry), new THREE.LineBasicMaterial({ color: 0xffc040 }));
edges.position.copy(center);
scene.add(edges);

const r = (n) => n.toFixed(0);
document.getElementById("dims").textContent =
  "Signing space (cm, glTF axes; character faces +Z)\\n" +
  "x " + r(space.min.x) + " to " + r(space.max.x) + "   (width " + r(size.x) + ")\\n" +
  "y " + r(space.min.y) + " to " + r(space.max.y) + "   (height " + r(size.y) + ")\\n" +
  "z " + r(space.min.z) + " to " + r(space.max.z) + "   (depth " + r(size.z) + ")";

// Frame both the character and the signing space
const sphere = space.clone().union(bbox).getBoundingSphere(new THREE.Sphere());
const hFov = 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * camera.aspect);
const dist = 1.05 * sphere.radius / Math.sin(Math.min(THREE.MathUtils.degToRad(camera.fov), hFov) / 2);

window.shoot = (label, dir) => {
  document.getElementById("lab").textContent = label;
  camera.position.copy(sphere.center).addScaledVector(new THREE.Vector3(...dir).normalize(), dist);
  camera.lookAt(sphere.center);
  renderer.render(scene, camera);
};
window.signingSpace = { min: space.min.toArray(), max: space.max.toArray() };
window.ready = true;
</script></body></html>`;
}

function combinedPage(files) {
  const imgs = files.map((f) => `<img src="/out/${f}" style="width:${VIEW_W}px;height:${VIEW_H}px;display:block">`).join("");
  return `<!doctype html><html><body style="margin:0"><div id="all" style="display:flex">${imgs}</div></body></html>`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!fs.existsSync(args.glb)) throw new Error(`Character not found: ${args.glb}`);
  fs.mkdirSync(args.out, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: VIEW_W * VIEWS.length, height: VIEW_H }, deviceScaleFactor: SCALE });
  page.on("pageerror", (e) => console.error("Page error:", e.message));

  // Serve everything from disk
  await page.route(`${ORIGIN}/**`, (route) => {
    const p = new URL(route.request().url()).pathname;
    if (p === "/scene.html") return route.fulfill({ contentType: "text/html; charset=utf-8", body: scenePage() });
    if (p === "/combined.html") return route.fulfill({ contentType: "text/html; charset=utf-8", body: combinedPage(VIEWS.map((v) => `signing-space-${v.file}.png`)) });
    if (p === "/character.glb") return route.fulfill({ contentType: "model/gltf-binary", body: fs.readFileSync(args.glb) });
    if (p.startsWith("/static/")) return route.fulfill({ contentType: "text/javascript", body: fs.readFileSync(path.join(STATIC_DIR, p.slice(8))) });
    if (p.startsWith("/out/")) return route.fulfill({ contentType: "image/png", body: fs.readFileSync(path.join(args.out, p.slice(5))) });
    return route.fulfill({ status: 404 });
  });

  await page.goto(`${ORIGIN}/scene.html`);
  await page.waitForFunction(() => window.ready, null, { timeout: 60000 });
  for (const v of VIEWS) {
    await page.evaluate(([l, d]) => window.shoot(l, d), [v.label, v.dir]);
    const file = path.join(args.out, `signing-space-${v.file}.png`);
    await page.locator("#c").screenshot({ path: file });
    console.log("Saved", file);
  }
  const space = await page.evaluate(() => window.signingSpace);

  await page.goto(`${ORIGIN}/combined.html`);
  await page.waitForFunction(() => [...document.images].every((i) => i.complete && i.naturalWidth > 0));
  const all = path.join(args.out, "signing-space-all.png");
  await page.locator("#all").screenshot({ path: all });
  console.log("Saved", all);
  console.log("Signing space (cm): min", space.min.map((n) => n.toFixed(1)), "max", space.max.map((n) => n.toFixed(1)));

  await browser.close();
}

main().catch((e) => { console.error(e.message); process.exit(1); });
