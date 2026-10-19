/* MMS-Player web editor: real-time 3D preview of the animation data exported with `main.py --export-preview-json`.
 *
 * Exposes window.MMSViewer3D for the (non-module) app.js, and fires the "mmsviewer3d-ready" event on window.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const BOOT = window.MMSWEB_BOOT;
const $ = (sel) => document.querySelector(sel);

const view = {
  initialized: false,
  loading: null,          // Promise of the character loading
  renderer: null, scene: null, camera: null, controls: null,
  homePos: null, homeTarget: null,
  signingSpace: null,     // Box3 reachable by the hands, framed by the preset views
  bones: [],              // per animated bone: Object3D or null
  morphMaps: [],          // per mesh: {mesh, idx: Int32Array (anim morph index -> mesh morph index, -1 if none)}
  needsRender: true,
  active: false,          // the 3D tab is visible
};

const play = {
  anim: null,             // {fps, frames, nb, pos, quat, scale, morphs, nm, glosses}
  label: "",
  time: 0,
  playing: false,
  speed: 1,
  loop: true,
  scrubbing: false,       // the user is dragging the time slider: playback is suspended
  last: 0,
};

const timeListeners = [];
const tmpQuat = [0, 0, 0, 1];

function setStatus(html) {
  const s = $("#v3d-status");
  // Wrapped in a single element: the overlay is a flex box, which would drop the spaces around <b>/<code>.
  s.innerHTML = html ? `<span>${html}</span>` : "";
  s.classList.toggle("hidden", !html);
}

//
// Scene setup
//
function failInit(html, message) {
  setStatus(html);
  view.loading = Promise.reject(new Error(message));
  view.loading.catch(() => {});
  return view.loading;
}

function init() {
  if (view.loading) return view.loading;
  if (!BOOT.character_url) {
    return failInit("The 3D character is missing.<br>Run <code>tools/export_character_glb.py</code> in the MMS-Player folder.",
      "character missing");
  }

  const box = $("#v3d-canvas-box");
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch (e) {
    return failInit("The 3D preview needs WebGL, which is not available in this browser.", "WebGL not available");
  }
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.toneMapping = THREE.NeutralToneMapping;
  box.prepend(renderer.domElement);
  view.renderer = renderer;

  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8070, 1.6));
  const key = new THREE.DirectionalLight(0xffffff, 1.8);
  key.position.set(80, 250, 250);
  scene.add(key);
  const back = new THREE.DirectionalLight(0xffffff, 0.8);
  back.position.set(-150, 200, -200);
  scene.add(back);
  const grid = new THREE.GridHelper(300, 30, 0x888888, 0xbbbbbb);
  grid.material.transparent = true;
  grid.material.opacity = 0.35;
  scene.add(grid);
  view.scene = scene;

  // Units are centimeters, as in the Blender scene.
  view.camera = new THREE.PerspectiveCamera(40, 9 / 16, 1, 5000);
  view.controls = new OrbitControls(view.camera, renderer.domElement);
  view.controls.enableDamping = true;
  view.controls.addEventListener("change", () => { view.needsRender = true; });

  new ResizeObserver(resize).observe(box);
  resize();
  requestAnimationFrame(loop);

  setStatus("Loading the 3D character…");
  view.loading = new GLTFLoader().loadAsync(BOOT.character_url).then((gltf) => {
    scene.add(gltf.scene);
    gltf.scene.updateMatrixWorld(true);
    setupHomeView(gltf);
    view.initialized = true;
    if (play.anim) bindAnimation();
    setStatus(play.anim ? "" : "Press <b>Preview 3D</b> to animate the character.");
    view.needsRender = true;
  }).catch((e) => {
    setStatus("Can not load the 3D character: " + e.message);
    throw e;
  });
  return view.loading;
}

function setupHomeView(gltf) {
  // Start from the same point of view of the rendering camera, if available.
  const bbox = new THREE.Box3();
  gltf.scene.traverse((o) => { if (o.isSkinnedMesh || o.isMesh) bbox.expandByObject(o); });
  const center = bbox.getCenter(new THREE.Vector3());
  const cam = gltf.cameras && gltf.cameras[0];
  if (cam) {
    cam.updateMatrixWorld(true);
    const pos = cam.getWorldPosition(new THREE.Vector3());
    const dir = cam.getWorldDirection(new THREE.Vector3());
    const dist = pos.distanceTo(center);
    view.homePos = pos;
    view.homeTarget = pos.clone().addScaledVector(dir, dist);
    view.camera.fov = cam.fov;
  } else {
    const size = bbox.getSize(new THREE.Vector3());
    view.homeTarget = center;
    view.homePos = center.clone().add(new THREE.Vector3(0, 0, size.y * 1.6));
  }
  view.camera.updateProjectionMatrix();
  view.signingSpace = computeSigningSpace(gltf.scene, bbox);
  resetView();
}

/** The volume where the hands move, estimated from the character in rest (T) pose. */
function computeSigningSpace(root, bbox) {
  const pos = (name) => {
    const o = root.getObjectByName(name);
    return o ? o.getWorldPosition(new THREE.Vector3()) : null;
  };
  const head = pos("Bone_Head"), pelvis = pos("Bone_Pelvis"), shoulder = pos("Bone_R_UpperArm");
  if (!head || !pelvis || !shoulder) return bbox.clone();
  // In T-pose, the bounding box spans from fingertip to fingertip.
  const reach = bbox.max.x - Math.abs(shoulder.x - head.x) - head.x;
  return new THREE.Box3(
    new THREE.Vector3(head.x - 0.7 * reach, pelvis.y, bbox.min.z),
    new THREE.Vector3(head.x + 0.7 * reach, bbox.max.y + 0.15 * reach, head.z + 0.85 * reach));
}

function resetView() {
  if (!view.homePos) return;
  view.camera.position.copy(view.homePos);
  view.controls.target.copy(view.homeTarget);
  view.controls.update();
  view.needsRender = true;
}

// Directions from the target to the camera for the preset views. The character faces +Z, so her left side is +X.
// The top view is slightly tilted to the front, so that the orbit controls keep the character's front downwards.
const VIEW_DIRECTIONS = {
  top: new THREE.Vector3(0, 1, 0.001),
  left: new THREE.Vector3(1, 0, 0),
  right: new THREE.Vector3(-1, 0, 0),
};

/** Look at the character from the given side ("top", "left", "right"), framing the whole signing space. */
function presetView(name) {
  const space = view.signingSpace;
  if (!space) return;
  const center = space.getCenter(new THREE.Vector3());
  const size = space.getSize(new THREE.Vector3());
  // Extents of the signing space across the screen, along the screen, and along the view direction.
  const [across, along, depth] = name === "top" ? [size.x, size.z, size.y] : [size.z, size.y, size.x];
  const tanV = Math.tan(THREE.MathUtils.degToRad(view.camera.fov) / 2);
  const fit = Math.max(along / 2 / tanV, across / 2 / (tanV * view.camera.aspect));
  const dist = 1.05 * fit + depth / 2;
  view.controls.target.copy(center);
  view.camera.position.copy(center).addScaledVector(VIEW_DIRECTIONS[name].clone().normalize(), dist);
  view.controls.update();
  view.needsRender = true;
}

function resize() {
  const box = $("#v3d-canvas-box");
  const w = box.clientWidth, h = box.clientHeight;
  if (!view.renderer || w === 0 || h === 0) return;
  view.renderer.setSize(w, h, false);
  view.camera.aspect = w / h;
  view.camera.updateProjectionMatrix();
  view.needsRender = true;
}

//
// Animation data
//
function prepareAnimation(data) {
  if (data.format !== "mms-preview") throw new Error("Unknown animation format: " + data.format);
  const frames = data.frame_count;
  const nb = data.bones.length;
  const flat = (rows, n) => {
    const out = new Float32Array(frames * n);
    rows.forEach((r, i) => out.set(r, i * n));
    return out;
  };
  const nm = data.morph_names.length;
  return {
    fps: data.fps, frames, nb, nm,
    frameStart: data.frame_start,
    boneNames: data.bones,
    morphNames: data.morph_names,
    pos: flat(data.tracks.position, nb * 3),
    quat: flat(data.tracks.quaternion, nb * 4),
    scale: flat(data.tracks.scale, nb * 3),
    morphs: nm ? flat(data.morphs, nm) : null,
    glosses: data.glosses || [],
  };
}

function bindAnimation() {
  const a = play.anim;
  const root = view.scene;
  view.bones = a.boneNames.map((n) => root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(n)) || null);
  const missing = a.boneNames.filter((_n, i) => !view.bones[i]);
  if (missing.length) console.warn("MMSViewer3D: bones not found in the character:", missing);

  view.morphMaps = [];
  root.traverse((o) => {
    if (!o.isMesh || !o.morphTargetDictionary) return;
    const idx = new Int32Array(a.nm).fill(-1);
    a.morphNames.forEach((n, i) => { if (n in o.morphTargetDictionary) idx[i] = o.morphTargetDictionary[n]; });
    view.morphMaps.push({ mesh: o, idx });
  });
}

function applyPose(t) {
  const a = play.anim;
  if (!a || !view.initialized) return;
  const f = Math.min(Math.max(t * a.fps, 0), a.frames - 1);
  const i0 = Math.floor(f);
  const i1 = Math.min(i0 + 1, a.frames - 1);
  const k = f - i0;
  const nb = a.nb;

  for (let b = 0; b < nb; b++) {
    const bone = view.bones[b];
    if (!bone) continue;
    let o0 = (i0 * nb + b) * 3, o1 = (i1 * nb + b) * 3;
    bone.position.set(
      a.pos[o0] + (a.pos[o1] - a.pos[o0]) * k,
      a.pos[o0 + 1] + (a.pos[o1 + 1] - a.pos[o0 + 1]) * k,
      a.pos[o0 + 2] + (a.pos[o1 + 2] - a.pos[o0 + 2]) * k);
    bone.scale.set(
      a.scale[o0] + (a.scale[o1] - a.scale[o0]) * k,
      a.scale[o0 + 1] + (a.scale[o1 + 1] - a.scale[o0 + 1]) * k,
      a.scale[o0 + 2] + (a.scale[o1 + 2] - a.scale[o0 + 2]) * k);
    o0 = (i0 * nb + b) * 4; o1 = (i1 * nb + b) * 4;
    THREE.Quaternion.slerpFlat(tmpQuat, 0, a.quat, o0, a.quat, o1, k);
    bone.quaternion.fromArray(tmpQuat);
  }

  if (a.morphs) {
    const nm = a.nm;
    for (const { mesh, idx } of view.morphMaps) {
      const w = mesh.morphTargetInfluences;
      for (let m = 0; m < nm; m++) {
        const j = idx[m];
        if (j < 0) continue;
        const v0 = a.morphs[i0 * nm + m], v1 = a.morphs[i1 * nm + m];
        w[j] = v0 + (v1 - v0) * k;
      }
    }
  }

  // Gloss subtitle
  const frame = a.frameStart + f;
  const g = a.glosses.find((s) => frame >= s.start && frame <= s.end);
  $("#v3d-gloss").textContent = g ? g.gloss.replace(/^maingloss:/, "") : "";
  view.needsRender = true;
}

//
// Playback
//
const duration = () => (play.anim ? (play.anim.frames - 1) / play.anim.fps : 0);

function fmt(t) {
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}

// Write to the DOM only when a value changes: rewriting the controls at every frame breaks the dragging of the
// slider and the clicks on the play button in Safari.
function setProp(elem, prop, value) {
  if (elem[prop] !== value) elem[prop] = value;
}

function updateControls() {
  const d = duration();
  const btn = $("#v3d-play");
  setProp(btn, "textContent", play.playing ? "❚❚" : "▶");
  setProp(btn, "disabled", !play.anim);
  const scrub = $("#v3d-scrub");
  setProp(scrub, "disabled", !play.anim);
  setProp(scrub, "max", String(d));
  if (!play.scrubbing) setProp(scrub, "value", String(play.time));
  setProp($("#v3d-time"), "textContent", `${fmt(play.time)} / ${fmt(d)}`);
}

function setTime(t, notify = true) {
  play.time = Math.min(Math.max(t, 0), duration());
  applyPose(play.time);
  updateControls();
  if (notify) for (const cb of timeListeners) cb(play.time);
}

function loop(now) {
  requestAnimationFrame(loop);
  const dt = play.last ? (now - play.last) / 1000 : 0;
  play.last = now;
  if (play.playing && !play.scrubbing && play.anim && view.initialized) {
    let t = play.time + dt * play.speed;
    const d = duration();
    if (t >= d) {
      if (play.loop && d > 0) t = t % d;
      else { t = d; play.playing = false; }
    }
    setTime(t);
  }
  if (view.controls) view.controls.update();
  if (view.active && view.needsRender && view.renderer) {
    view.needsRender = false;
    view.renderer.render(view.scene, view.camera);
  }
}

function setupControls() {
  $("#v3d-play").addEventListener("click", () => api.toggle());
  // Dragging or clicking the slider seeks; the playback (if active) continues once the slider is released.
  const scrub = $("#v3d-scrub");
  const endScrub = () => { play.scrubbing = false; };
  scrub.addEventListener("pointerdown", () => { play.scrubbing = true; });
  scrub.addEventListener("pointerup", endScrub);
  scrub.addEventListener("pointercancel", endScrub);
  scrub.addEventListener("change", endScrub);
  scrub.addEventListener("input", () => setTime(Number(scrub.value)));
  $("#v3d-speed").addEventListener("change", (e) => { play.speed = Number(e.target.value); });
  $("#v3d-loop").addEventListener("change", (e) => { play.loop = e.target.checked; });
  $("#v3d-reset").addEventListener("click", resetView);
  for (const name of Object.keys(VIEW_DIRECTIONS)) {
    $(`#v3d-view-${name}`).addEventListener("click", () => presetView(name));
  }
  $("#v3d-canvas-box").addEventListener("keydown", (e) => {
    if (e.key === " ") { e.preventDefault(); api.toggle(); }
  });
  updateControls();
}

const api = {
  /** Load the character (once). Returns a Promise. */
  init,
  /** Show the animation data (parsed JSON of the mms-preview format). */
  async load(data, label = "") {
    play.anim = prepareAnimation(data);
    play.label = label;
    $("#v3d-caption").textContent = label;
    try { await init(); } catch (e) { return; }
    bindAnimation();
    setStatus("");
    setTime(0);
  },
  play() {
    if (!play.anim) return;
    if (play.time >= duration()) play.time = 0;
    play.playing = true;
    updateControls();
  },
  pause() { play.playing = false; updateControls(); },
  toggle() { if (play.playing) api.pause(); else api.play(); },
  seek(t) { setTime(t); },
  /** The 3D view is visible or not: no rendering while hidden. */
  setActive(active) {
    view.active = active;
    if (active) { init().catch(() => {}); resize(); view.needsRender = true; } else api.pause();
  },
  onTime(cb) { timeListeners.push(cb); },
  get hasAnimation() { return !!play.anim; },
  get time() { return play.time; },
  get label() { return play.label; },
};

setupControls();
window.MMSViewer3D = api;
window.dispatchEvent(new Event("mmsviewer3d-ready"));
