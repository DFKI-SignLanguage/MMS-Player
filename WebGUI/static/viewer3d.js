/* MMS-Player web editor: real-time 3D preview of the animation data exported with `main.py --export-preview-json`.
 *
 * Every element with the "v3d" class (see the viewer3d macro in index.html) becomes a viewer.
 * Exposes window.MMSViewers = {<data-viewer name>: viewer, ...} (e.g. "main", "sign") for the (non-module) app.js,
 * and fires the "mmsviewer3d-ready" event on window.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import * as SkeletonUtils from "three/addons/utils/SkeletonUtils.js";

const BOOT = window.MMSWEB_BOOT;

const tmpQuat = [0, 0, 0, 1];

// Directions from the target to the camera for the preset views. The character faces +Z, so her left side is +X.
// The top view is slightly tilted to the front, so that the orbit controls keep the character's front downwards.
const VIEW_DIRECTIONS = {
  top: new THREE.Vector3(0, 1, 0.001),
  left: new THREE.Vector3(1, 0, 0),
  right: new THREE.Vector3(-1, 0, 0),
};

//
// The character, loaded once and shared (as clones) by all the viewers
//
let characterPromise = null;

function loadCharacter() {
  if (!characterPromise) {
    characterPromise = new GLTFLoader().loadAsync(BOOT.character_url).then((gltf) => {
      gltf.scene.updateMatrixWorld(true);
      const bbox = new THREE.Box3();
      gltf.scene.traverse((o) => { if (o.isSkinnedMesh || o.isMesh) bbox.expandByObject(o); });
      return { scene: gltf.scene, bbox, ...homeView(gltf, bbox), signingSpace: computeSigningSpace(gltf.scene, bbox) };
    });
  }
  return characterPromise;
}

/** Start from the same point of view of the rendering camera, if available. */
function homeView(gltf, bbox) {
  const center = bbox.getCenter(new THREE.Vector3());
  const cam = gltf.cameras && gltf.cameras[0];
  if (cam) {
    cam.updateMatrixWorld(true);
    const pos = cam.getWorldPosition(new THREE.Vector3());
    const dir = cam.getWorldDirection(new THREE.Vector3());
    return { homePos: pos, homeTarget: pos.clone().addScaledVector(dir, pos.distanceTo(center)), fov: cam.fov };
  }
  const size = bbox.getSize(new THREE.Vector3());
  return { homePos: center.clone().add(new THREE.Vector3(0, 0, size.y * 1.6)), homeTarget: center, fov: 40 };
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

function fmt(t) {
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}

// Write to the DOM only when a value changes: rewriting the controls at every frame breaks the dragging of the
// slider and the clicks on the play button in Safari.
function setProp(elem, prop, value) {
  if (elem[prop] !== value) elem[prop] = value;
}

//
// A viewer, bound to its root element
//
class Viewer3D {
  constructor(root) {
    this.root = root;
    this.el = (cls) => root.querySelector("." + cls);
    // The message shown when the character is ready, but nothing is loaded yet.
    this.idleHtml = this.el("v3d-status").innerHTML;

    this.initialized = false;
    this.loading = null;          // Promise of the scene initialization
    this.renderer = null; this.scene = null; this.camera = null; this.controls = null;
    this.character = null;        // shared character data (home view, signing space)
    this.bones = [];              // per animated bone: Object3D or null
    this.morphMaps = [];          // per mesh: {mesh, idx: Int32Array (anim morph index -> mesh morph index, -1 if none)}
    this.needsRender = true;
    this.active = false;          // the viewer is visible

    this.anim = null;             // {fps, frames, nb, pos, quat, scale, morphs, nm, glosses}
    this.label = "";
    this.time = 0;
    this.playing = false;
    this.speed = 1;
    this.loop = true;
    this.scrubbing = false;       // the user is dragging the time slider: playback is suspended
    this.last = 0;
    this.timeListeners = [];

    this.setupControls();
  }

  setStatus(html) {
    const s = this.el("v3d-status");
    // Wrapped in a single element: the overlay is a flex box, which would drop the spaces around <b>/<code>.
    s.innerHTML = html ? `<span>${html}</span>` : "";
    s.classList.toggle("hidden", !html);
  }

  //
  // Scene setup
  //
  failInit(html, message) {
    this.setStatus(html);
    this.loading = Promise.reject(new Error(message));
    this.loading.catch(() => {});
    return this.loading;
  }

  /** Create the scene and load the character (once). Returns a Promise. */
  init() {
    if (this.loading) return this.loading;
    if (!BOOT.character_url) {
      return this.failInit("The 3D character is missing.<br>Run <code>tools/export_character_glb.py</code> in the MMS-Player folder.",
        "character missing");
    }

    const box = this.el("v3d-canvas-box");
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch (e) {
      return this.failInit("The 3D preview needs WebGL, which is not available in this browser.", "WebGL not available");
    }
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.toneMapping = THREE.NeutralToneMapping;
    box.prepend(renderer.domElement);
    this.renderer = renderer;

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
    this.scene = scene;

    // Units are centimeters, as in the Blender scene.
    this.camera = new THREE.PerspectiveCamera(40, 9 / 16, 1, 5000);
    this.controls = new OrbitControls(this.camera, renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.addEventListener("change", () => { this.needsRender = true; });

    new ResizeObserver(() => this.resize()).observe(box);
    this.resize();
    const loop = (now) => { requestAnimationFrame(loop); this.frame(now); };
    requestAnimationFrame(loop);

    this.setStatus("Loading the 3D character…");
    this.loading = loadCharacter().then((character) => {
      this.character = character;
      scene.add(SkeletonUtils.clone(character.scene));
      this.camera.fov = character.fov;
      this.camera.updateProjectionMatrix();
      this.resetView();
      this.initialized = true;
      if (this.anim) this.bindAnimation();
      this.setStatus(this.anim ? "" : this.idleHtml);
      this.needsRender = true;
    }).catch((e) => {
      this.setStatus("Can not load the 3D character: " + e.message);
      throw e;
    });
    return this.loading;
  }

  resetView() {
    const c = this.character;
    if (!c) return;
    this.camera.position.copy(c.homePos);
    this.controls.target.copy(c.homeTarget);
    this.controls.update();
    this.needsRender = true;
  }

  /** Look at the character from the given side ("top", "left", "right"), framing the whole signing space. */
  presetView(name) {
    const space = this.character && this.character.signingSpace;
    if (!space) return;
    const center = space.getCenter(new THREE.Vector3());
    const size = space.getSize(new THREE.Vector3());
    // Extents of the signing space across the screen, along the screen, and along the view direction.
    const [across, along, depth] = name === "top" ? [size.x, size.z, size.y] : [size.z, size.y, size.x];
    const tanV = Math.tan(THREE.MathUtils.degToRad(this.camera.fov) / 2);
    const fit = Math.max(along / 2 / tanV, across / 2 / (tanV * this.camera.aspect));
    const dist = 1.05 * fit + depth / 2;
    this.controls.target.copy(center);
    this.camera.position.copy(center).addScaledVector(VIEW_DIRECTIONS[name].clone().normalize(), dist);
    this.controls.update();
    this.needsRender = true;
  }

  resize() {
    const box = this.el("v3d-canvas-box");
    const w = box.clientWidth, h = box.clientHeight;
    if (!this.renderer || w === 0 || h === 0) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.needsRender = true;
  }

  //
  // Animation
  //
  bindAnimation() {
    const a = this.anim;
    const root = this.scene;
    this.bones = a.boneNames.map((n) => root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(n)) || null);
    const missing = a.boneNames.filter((_n, i) => !this.bones[i]);
    if (missing.length) console.warn("MMSViewer3D: bones not found in the character:", missing);

    this.morphMaps = [];
    root.traverse((o) => {
      if (!o.isMesh || !o.morphTargetDictionary) return;
      const idx = new Int32Array(a.nm).fill(-1);
      a.morphNames.forEach((n, i) => { if (n in o.morphTargetDictionary) idx[i] = o.morphTargetDictionary[n]; });
      this.morphMaps.push({ mesh: o, idx });
    });
  }

  applyPose(t) {
    const a = this.anim;
    if (!a || !this.initialized) return;
    const f = Math.min(Math.max(t * a.fps, 0), a.frames - 1);
    const i0 = Math.floor(f);
    const i1 = Math.min(i0 + 1, a.frames - 1);
    const k = f - i0;
    const nb = a.nb;

    for (let b = 0; b < nb; b++) {
      const bone = this.bones[b];
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
      for (const { mesh, idx } of this.morphMaps) {
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
    setProp(this.el("v3d-gloss"), "textContent", g ? g.gloss.replace(/^maingloss:/, "") : "");
    this.needsRender = true;
  }

  //
  // Playback
  //
  get duration() { return this.anim ? (this.anim.frames - 1) / this.anim.fps : 0; }

  updateControls() {
    const d = this.duration;
    const btn = this.el("v3d-play");
    setProp(btn, "textContent", this.playing ? "❚❚" : "▶");
    setProp(btn, "disabled", !this.anim);
    const scrub = this.el("v3d-scrub");
    setProp(scrub, "disabled", !this.anim);
    setProp(scrub, "max", String(d));
    if (!this.scrubbing) setProp(scrub, "value", String(this.time));
    setProp(this.el("v3d-time"), "textContent", `${fmt(this.time)} / ${fmt(d)}`);
  }

  setTime(t, notify = true) {
    this.time = Math.min(Math.max(t, 0), this.duration);
    this.applyPose(this.time);
    this.updateControls();
    if (notify) for (const cb of this.timeListeners) cb(this.time);
  }

  frame(now) {
    const dt = this.last ? (now - this.last) / 1000 : 0;
    this.last = now;
    if (this.playing && !this.scrubbing && this.anim && this.initialized) {
      let t = this.time + dt * this.speed;
      const d = this.duration;
      if (t >= d) {
        if (this.loop && d > 0) t = t % d;
        else { t = d; this.playing = false; }
      }
      this.setTime(t);
    }
    if (this.controls) this.controls.update();
    if (this.active && this.needsRender && this.renderer) {
      this.needsRender = false;
      this.renderer.render(this.scene, this.camera);
    }
  }

  setupControls() {
    this.el("v3d-play").addEventListener("click", () => this.toggle());
    // Dragging or clicking the slider seeks; the playback (if active) continues once the slider is released.
    const scrub = this.el("v3d-scrub");
    const endScrub = () => { this.scrubbing = false; };
    scrub.addEventListener("pointerdown", () => { this.scrubbing = true; });
    scrub.addEventListener("pointerup", endScrub);
    scrub.addEventListener("pointercancel", endScrub);
    scrub.addEventListener("change", endScrub);
    scrub.addEventListener("input", () => this.setTime(Number(scrub.value)));
    this.el("v3d-speed").addEventListener("change", (e) => { this.speed = Number(e.target.value); });
    this.el("v3d-loop").addEventListener("change", (e) => { this.loop = e.target.checked; });
    this.el("v3d-reset").addEventListener("click", () => this.resetView());
    for (const name of Object.keys(VIEW_DIRECTIONS)) {
      this.el(`v3d-view-${name}`).addEventListener("click", () => this.presetView(name));
    }
    this.el("v3d-canvas-box").addEventListener("keydown", (e) => {
      if (e.key === " ") { e.preventDefault(); this.toggle(); }
    });
    this.updateControls();
  }

  //
  // Public API
  //
  /** Show the animation data (parsed JSON of the mms-preview format). */
  async load(data, label = "") {
    this.anim = prepareAnimation(data);
    this.label = label;
    this.el("v3d-caption").textContent = label;
    try { await this.init(); } catch (e) { return; }
    this.bindAnimation();
    this.setStatus("");
    this.setTime(0);
  }

  /** Remove the animation (the character stays in its last pose), and show a message. */
  clear(html = "") {
    this.anim = null;
    this.playing = false;
    this.label = "";
    this.el("v3d-caption").textContent = "";
    this.el("v3d-gloss").textContent = "";
    this.time = 0;
    this.updateControls();
    this.setStatus(html);
  }

  play() {
    if (!this.anim) return;
    if (this.time >= this.duration) this.time = 0;
    this.playing = true;
    this.updateControls();
  }

  pause() { this.playing = false; this.updateControls(); }
  toggle() { if (this.playing) this.pause(); else this.play(); }
  seek(t) { this.setTime(t); }

  /** Start time (s) of the given MMS row in the loaded animation, or null if not known. */
  glossStart(row) {
    const a = this.anim;
    const g = a && a.glosses.find((s) => s.index === row);
    return g ? (g.start - a.frameStart) / a.fps : null;
  }

  /** The viewer is visible or not: no rendering while hidden. */
  setActive(active) {
    this.active = active;
    if (active) { this.init().catch(() => {}); this.resize(); this.needsRender = true; } else this.pause();
  }

  onTime(cb) { this.timeListeners.push(cb); }
  get hasAnimation() { return !!this.anim; }
}

const viewers = {};
for (const root of document.querySelectorAll(".v3d")) viewers[root.dataset.viewer] = new Viewer3D(root);
window.MMSViewers = viewers;
window.dispatchEvent(new Event("mmsviewer3d-ready"));
