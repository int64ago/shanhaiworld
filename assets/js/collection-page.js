import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { KTX2Loader } from "three/addons/loaders/KTX2Loader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

const canvas = document.querySelector("#scene-canvas");
const loadingState = document.querySelector("#loading-state");
const loadingDetail = document.querySelector("#loading-detail");
const errorPanel = document.querySelector("#viewer-error");
const errorMessage = document.querySelector("#viewer-error-message");
const actionSelect = document.querySelector("#action-select");
const roamButton = document.querySelector("#toggle-roam");
const resetButton = document.querySelector("#reset-camera");
const configUrl = new URL(document.body.dataset.collectionConfig || "./collection.json", window.location.href);

const clock = new THREE.Clock();
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const actor = new THREE.Group();
const motionRoot = new THREE.Group();
const roamDirection = new THREE.Vector3();
const followTarget = new THREE.Vector3();
const followDelta = new THREE.Vector3();
const disposableTextures = new Set();
const disposableRoots = [];
const runtimeMetrics = {
  status: "loading",
  started_at: performance.now(),
  frames: 0,
  average_fps: 0,
  draw_calls: 0,
  rendered_triangles: 0,
};

globalThis.__shanhaiworldMetrics = runtimeMetrics;

let config;
let modelRoot;
let mixer;
let activeAction;
let availableClips = [];
let roamEnabled = true;
let roamMode = "idle";
let roamUntil = 0;
let destination = new THREE.Vector3();
let pointerDown = null;

actor.add(motionRoot);

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  alpha: false,
  powerPreference: "high-performance",
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.08;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color("#07100e");
scene.add(actor);

const camera = new THREE.PerspectiveCamera(42, window.innerWidth / window.innerHeight, 0.08, 160);
const defaultCameraPosition = new THREE.Vector3(6.8, 3.7, 8.6);
camera.position.copy(defaultCameraPosition);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.055;
controls.minDistance = 3.5;
controls.maxDistance = 20;
controls.minPolarAngle = 0.36;
controls.maxPolarAngle = Math.PI * 0.49;
controls.target.set(0, 1.35, 0);
controls.update();

const loader = new GLTFLoader();
const dracoLoader = new DRACOLoader();
const threeLibraries = new URL("../vendor/three/examples/jsm/libs/", import.meta.url);
dracoLoader.setDecoderPath(new URL("draco/gltf/", threeLibraries).href);
const ktx2Loader = new KTX2Loader();
ktx2Loader.setTranscoderPath(new URL("basis/", threeLibraries).href);
ktx2Loader.detectSupport(renderer);
loader.setDRACOLoader(dracoLoader);
loader.setKTX2Loader(ktx2Loader);
loader.setMeshoptDecoder(MeshoptDecoder);

function assetUrl(path) {
  return new URL(path, configUrl).href;
}

function hexColor(value, fallback) {
  try {
    return new THREE.Color(value || fallback);
  } catch {
    return new THREE.Color(fallback);
  }
}

async function fetchConfig() {
  const response = await fetch(configUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`无法读取神兽配置（${response.status}）`);
  return response.json();
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value || "";
}

function renderMetadata() {
  document.title = `${config.name} · 山海万象`;
  setText("#creature-name", config.name);
  setText("#creature-kicker", config.subtitle || "SHANHAI CREATURE");
  setText("#creature-summary", config.summary || "一只从古籍记载中苏醒的山海神兽。");

  const facts = document.querySelector("#creature-facts");
  const rows = Array.isArray(config.facts) ? [...config.facts] : [];
  if (config.body_type) rows.unshift({ label: "形态", value: config.body_type });

  const fragment = document.createDocumentFragment();
  rows.slice(0, 5).forEach((row) => {
    const term = document.createElement("dt");
    const value = document.createElement("dd");
    term.textContent = row.label;
    value.textContent = row.value;
    fragment.append(term, value);
  });
  facts.replaceChildren(fragment);
}

function configureCamera() {
  const values = config.camera || {};
  if (Array.isArray(values.position)) defaultCameraPosition.fromArray(values.position);
  camera.position.copy(defaultCameraPosition);
  if (Array.isArray(values.target)) controls.target.fromArray(values.target);
  controls.minDistance = values.min_distance ?? 3.5;
  controls.maxDistance = values.max_distance ?? 20;
  controls.update();
}

function addLighting() {
  const values = config.lighting || {};
  const hemisphere = new THREE.HemisphereLight(
    hexColor(values.ambient_color, "#a8c9b9"),
    hexColor(config.scene?.ground_color, "#17231d"),
    values.ambient_intensity ?? 1.25,
  );
  scene.add(hemisphere);

  const sun = new THREE.DirectionalLight(
    hexColor(values.sun_color, "#f1d3a0"),
    values.sun_intensity ?? 2.8,
  );
  const position = values.sun_position || [6, 10, 4];
  sun.position.fromArray(position);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.near = 0.5;
  sun.shadow.camera.far = 40;
  sun.shadow.camera.left = -12;
  sun.shadow.camera.right = 12;
  sun.shadow.camera.top = 12;
  sun.shadow.camera.bottom = -12;
  scene.add(sun);
}

function addGround() {
  const values = config.scene || {};
  const size = values.ground_size || 42;
  const opacity = values.ground_opacity ?? 1;
  const geometry = new THREE.CircleGeometry(size * 0.5, 96);
  const material = new THREE.MeshStandardMaterial({
    color: hexColor(values.ground_color, "#17231d"),
    roughness: 0.96,
    metalness: 0.02,
    transparent: opacity < 1,
    opacity,
  });
  const ground = new THREE.Mesh(geometry, material);
  ground.name = "ShanhaiworldGround";
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  disposableRoots.push(ground);
}

function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function addEnvironmentAccents() {
  const values = config.scene?.procedural_props;
  if (!values?.enabled) return;

  const waterGeometry = new THREE.CircleGeometry(values.water_radius || 13, 96);
  const waterMaterial = new THREE.MeshPhysicalMaterial({
    color: hexColor(values.water_color, "#173b3a"),
    roughness: 0.22,
    metalness: 0.05,
    transparent: true,
    opacity: values.water_opacity ?? 0.5,
    depthWrite: false,
  });
  const water = new THREE.Mesh(waterGeometry, waterMaterial);
  water.name = "QingqiuShallowWater";
  water.rotation.x = -Math.PI / 2;
  water.position.y = 0.012;
  water.receiveShadow = true;
  scene.add(water);
  disposableRoots.push(water);

  const rockCount = Math.min(40, Math.max(0, values.rock_count ?? 20));
  const rockGeometry = new THREE.DodecahedronGeometry(0.55, 1);
  const rockMaterial = new THREE.MeshStandardMaterial({
    color: hexColor(values.rock_color, "#314d48"),
    roughness: 0.94,
    metalness: 0.04,
  });
  const rocks = new THREE.InstancedMesh(rockGeometry, rockMaterial, rockCount);
  rocks.name = "QingqiuJadeRocks";
  rocks.castShadow = true;
  rocks.receiveShadow = true;
  const matrix = new THREE.Matrix4();
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  const rotation = new THREE.Euler();
  const random = seededRandom(0x5190f0);
  const inner = (config.roaming?.bounds ?? 6) + 1.8;
  const outer = Math.max(inner + 1, values.rock_radius || 15);
  for (let index = 0; index < rockCount; index += 1) {
    const angle = random() * Math.PI * 2;
    const radius = THREE.MathUtils.lerp(inner, outer, Math.sqrt(random()));
    position.set(Math.cos(angle) * radius, THREE.MathUtils.randFloat(-0.18, -0.02), Math.sin(angle) * radius);
    rotation.set(random() * 0.4, random() * Math.PI, random() * 0.35);
    quaternion.setFromEuler(rotation);
    scale.set(
      THREE.MathUtils.lerp(0.45, 1.4, random()),
      THREE.MathUtils.lerp(0.35, 1.05, random()),
      THREE.MathUtils.lerp(0.5, 1.65, random()),
    );
    matrix.compose(position, quaternion, scale);
    rocks.setMatrixAt(index, matrix);
  }
  rocks.instanceMatrix.needsUpdate = true;
  scene.add(rocks);
  disposableRoots.push(rocks);
}

async function loadBackground() {
  const values = config.scene || {};
  scene.background = hexColor(values.background_color, "#07100e");
  scene.fog = new THREE.Fog(
    hexColor(values.fog_color, values.background_color || "#101a17"),
    values.fog_near ?? 12,
    values.fog_far ?? 42,
  );

  if (!values.background) return;
  try {
    const texture = await new THREE.TextureLoader().loadAsync(assetUrl(values.background));
    if (values.background_mode === "equirectangular") {
      texture.mapping = THREE.EquirectangularReflectionMapping;
    }
    texture.colorSpace = THREE.SRGBColorSpace;
    scene.background = texture;
    disposableTextures.add(texture);
  } catch (error) {
    console.warn("场景背景未加载，已使用颜色与雾效后备。", error);
  }
}

async function loadProps() {
  if (!config.scene?.props) return;
  try {
    const gltf = await loader.loadAsync(assetUrl(config.scene.props));
    gltf.scene.name = "EnvironmentProps";
    gltf.scene.traverse((object) => {
      if (object.isMesh) {
        object.castShadow = true;
        object.receiveShadow = true;
      }
    });
    scene.add(gltf.scene);
    disposableRoots.push(gltf.scene);
  } catch (error) {
    console.warn("场景道具未加载，继续展示主体。", error);
  }
}

function normalizeModel(root) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  const targetHeight = config.model?.target_height || 2.6;
  if (size.y > 0) root.scale.multiplyScalar(targetHeight / size.y);

  root.updateMatrixWorld(true);
  box.setFromObject(root);
  const center = box.getCenter(new THREE.Vector3());
  root.position.x -= center.x;
  root.position.z -= center.z;
  root.position.y -= box.min.y;
  root.rotation.y = config.model?.facing_offset || 0;
}

async function loadCreature() {
  if (!config.model?.path) throw new Error("collection.json 缺少 model.path");
  const url = assetUrl(config.model.path);
  const gltf = await loader.loadAsync(url, (event) => {
    if (!event.total) return;
    const percent = Math.round((event.loaded / event.total) * 100);
    loadingDetail.textContent = `加载模型与动画 ${percent}%`;
  });

  modelRoot = gltf.scene;
  modelRoot.name = config.id || config.name;
  normalizeModel(modelRoot);
  let skinnedMeshCount = 0;
  let morphMeshCount = 0;
  const boneNames = new Set();
  const objectNames = new Set();
  modelRoot.traverse((object) => {
    if (object.isMesh) {
      object.castShadow = true;
      object.receiveShadow = true;
    }
    if (object.isSkinnedMesh) skinnedMeshCount += 1;
    if (object.isBone && object.name) boneNames.add(object.name.toLowerCase());
    if (object.name) objectNames.add(object.name.toLowerCase());
    if (
      object.isMesh
      && Array.isArray(object.morphTargetInfluences)
      && object.morphTargetInfluences.length
    ) {
      morphMeshCount += 1;
    }
  });
  motionRoot.add(modelRoot);
  disposableRoots.push(modelRoot);

  mixer = new THREE.AnimationMixer(modelRoot);
  availableClips = (gltf.animations || []).map(makeInPlaceClip);
  const minimumClips = Math.max(
    6,
    Number(config.animation?.min_actions ?? config.quality?.min_animation_clips) || 6,
  );
  if (availableClips.length < minimumClips) {
    throw new Error(`模型只有 ${availableClips.length} 个真实动作，发布至少需要 ${minimumClips} 个`);
  }

  const rootNames = new Set(["root", "scene", "armature", "model", "actor", "object", "motionroot"]);
  const boneTrackTargets = new Set();
  const morphTrackTargets = new Set();
  const articulatedTrackTargets = new Set();
  availableClips.forEach((clip) => {
    clip.tracks.forEach((track) => {
      const lowerName = track.name.toLowerCase();
      const boneMatch = lowerName.match(/\.bones\[([^\]]+)\]/u);
      if (boneMatch && boneNames.has(boneMatch[1])) boneTrackTargets.add(boneMatch[1]);
      if (lowerName.includes(".morphtargetinfluences")) {
        morphTrackTargets.add(lowerName.split(".morphtargetinfluences", 1)[0]);
      }

      const target = lowerName.split(".", 1)[0].replace(/^\//u, "");
      const isTransformTrack = /\.(position|quaternion|rotation|scale)$/u.test(lowerName);
      if (
        isTransformTrack
        && target
        && objectNames.has(target)
        && !boneNames.has(target)
        && !rootNames.has(target)
      ) {
        articulatedTrackTargets.add(target);
      }
    });
  });

  const minimumAnimatedNodes = Math.max(2, Number(config.animation?.min_animated_nodes) || 3);
  const evidence = {
    skeletal: skinnedMeshCount > 0 && boneNames.size > 0 && boneTrackTargets.size > 0,
    morph: morphMeshCount > 0 && morphTrackTargets.size > 0,
    articulated: articulatedTrackTargets.size >= minimumAnimatedNodes,
  };
  const motionMode = String(config.animation?.mode || "skeletal").toLowerCase();
  const validModes = new Set(["skeletal", "morph", "articulated", "hybrid"]);
  if (!validModes.has(motionMode)) {
    throw new Error(`未知 animation.mode：${motionMode}`);
  }
  const modePassed = motionMode === "hybrid"
    ? Object.values(evidence).filter(Boolean).length >= 2
    : evidence[motionMode];
  if (!modePassed) {
    const details = `skin=${skinnedMeshCount}, boneTracks=${boneTrackTargets.size}, morphMeshes=${morphMeshCount}, morphTracks=${morphTrackTargets.size}, articulatedNodes=${articulatedTrackTargets.size}`;
    throw new Error(`模型未提供声明的 ${motionMode} 运动证据（${details}），已阻止整体摇晃降级`);
  }

  document.body.dataset.motionMode = motionMode;
  document.body.dataset.skinnedMeshes = String(skinnedMeshCount);
  document.body.dataset.morphMeshes = String(morphMeshCount);
  document.body.dataset.animatedBodyNodes = String(
    new Set([...boneTrackTargets, ...morphTrackTargets, ...articulatedTrackTargets]).size,
  );
  document.body.dataset.animationClips = String(availableClips.length);
  setupActions();
}

const synonyms = {
  idle: ["idle", "stand", "breath", "rest", "待机", "呼吸"],
  observe: ["observe", "look", "alert", "watch", "观察", "警觉"],
  walk: ["walk", "walking", "行走", "步行"],
  run: ["run", "running", "gallop", "奔跑", "疾跑"],
  attack: ["attack", "bite", "claw", "strike", "攻击", "撕咬"],
  roar: ["roar", "howl", "call", "shout", "咆哮", "鸣叫"],
  hit: ["hit", "hurt", "damage", "受击"],
  jump: ["jump", "leap", "跳跃"],
  fly: ["fly", "flight", "glide", "飞行", "滑翔"],
};

function makeInPlaceClip(clip) {
  if (config.model?.in_place_root_motion === false) return clip;

  const locomotionWords = [...synonyms.walk, ...synonyms.run, ...synonyms.fly];
  const isLocomotion = locomotionWords.some((word) =>
    clip.name.toLowerCase().includes(word.toLowerCase()),
  );
  if (!isLocomotion) return clip;

  const roots = config.model?.root_motion_nodes || [
    "root",
    "hips",
    "pelvis",
    "armature",
    "mixamorighips",
  ];
  const prepared = clip.clone();
  prepared.tracks = prepared.tracks.map((track) => {
    const lowerName = track.name.toLowerCase();
    const isRootPosition = lowerName.endsWith(".position")
      && roots.some((root) => lowerName.includes(String(root).toLowerCase()));
    if (!isRootPosition || track.values.length < 3) return track;

    const result = track.clone();
    const anchorX = result.values[0];
    const anchorZ = result.values[2];
    for (let index = 0; index < result.values.length; index += 3) {
      result.values[index] = anchorX;
      result.values[index + 2] = anchorZ;
    }
    return result;
  });
  prepared.resetDuration();
  return prepared;
}

function resolveClip(keyOrName) {
  const clips = availableClips;
  if (!clips.length) return null;

  const configured = config.actions?.[keyOrName];
  const requested = Array.isArray(configured)
    ? configured
    : [configured || keyOrName];
  const exact = clips.find((clip) =>
    requested.some((name) => clip.name.toLowerCase() === String(name).toLowerCase()),
  );
  if (exact) return exact;

  const words = [...requested, ...(synonyms[keyOrName] || [])];
  return clips.find((clip) => words.some((word) => clip.name.toLowerCase().includes(word.toLowerCase()))) || null;
}

function playClip(keyOrName, { once = false } = {}) {
  const clip = resolveClip(keyOrName);
  if (!clip || !mixer) return false;

  const next = mixer.clipAction(clip);
  if (next === activeAction && next.isRunning()) return true;

  next.reset();
  next.enabled = true;
  next.setEffectiveTimeScale(1);
  next.setEffectiveWeight(1);
  next.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat, once ? 1 : Infinity);
  next.clampWhenFinished = once;
  next.play();

  if (activeAction && activeAction !== next) activeAction.crossFadeTo(next, 0.38, true);
  activeAction = next;
  actionSelect.value = clip.name;

  if (once) {
    const onFinished = (event) => {
      if (event.action !== next) return;
      mixer.removeEventListener("finished", onFinished);
      playClip("idle");
    };
    mixer.addEventListener("finished", onFinished);
  }
  return true;
}

function setupActions() {
  const clips = availableClips;
  actionSelect.replaceChildren();
  if (!clips.length) throw new Error("动作面板无法找到真实 GLB clips");

  clips.forEach((clip) => actionSelect.add(new Option(clip.name, clip.name)));
  actionSelect.disabled = false;
  roamButton.disabled = !(resolveClip("walk") || resolveClip("run") || resolveClip("fly"));
  playClip("idle") || playClip(clips[0].name);
}

function chooseRoamState(now) {
  if (!roamEnabled) return;
  const bounds = config.roaming?.bounds ?? 7;
  const canWalk = resolveClip("walk") || resolveClip("fly");
  const canRun = resolveClip("run");
  const shouldMove = Boolean(canWalk) && Math.random() > 0.34;

  if (!shouldMove) {
    roamMode = "idle";
    const choices = ["idle", "observe", "call", "display"].filter(
      (name) => resolveClip(name),
    );
    const selected = choices[Math.floor(Math.random() * choices.length)] || "idle";
    playClip(selected, { once: selected !== "idle" });
    roamUntil = now + THREE.MathUtils.randFloat(2.8, 6.2);
    return;
  }

  roamMode = canRun && Math.random() > 0.72 ? "run" : "walk";
  const angle = Math.random() * Math.PI * 2;
  const radius = THREE.MathUtils.randFloat(bounds * 0.35, bounds * 0.92);
  destination.set(Math.cos(angle) * radius, 0, Math.sin(angle) * radius);
  playClip(roamMode);
  roamUntil = now + THREE.MathUtils.randFloat(4, 8);
}

function updateRoaming(delta, elapsed) {
  if (!roamEnabled || !config.roaming?.enabled) return;
  if (elapsed >= roamUntil) chooseRoamState(elapsed);
  if (roamMode !== "walk" && roamMode !== "run") return;

  roamDirection.copy(destination).sub(actor.position);
  roamDirection.y = 0;
  const distance = roamDirection.length();
  if (distance < 0.35) {
    roamUntil = 0;
    roamMode = "idle";
    return;
  }

  roamDirection.normalize();
  const targetRotation = Math.atan2(roamDirection.x, roamDirection.z);
  const deltaAngle = Math.atan2(Math.sin(targetRotation - actor.rotation.y), Math.cos(targetRotation - actor.rotation.y));
  actor.rotation.y += deltaAngle * Math.min(1, delta * 4.2);

  const speed = roamMode === "run"
    ? config.roaming?.run_speed ?? 1.45
    : config.roaming?.walk_speed ?? 0.7;
  actor.position.addScaledVector(roamDirection, Math.min(distance, speed * delta));
}

function resetCamera() {
  followDelta.set(actor.position.x, 0, actor.position.z);
  camera.position.copy(defaultCameraPosition).add(followDelta);
  controls.target.set(actor.position.x, 1.35, actor.position.z);
  controls.update();
}

function triggerClickAction() {
  const choices = config.interaction?.click_actions || ["observe", "roar", "attack"];
  const available = choices.filter((name) => resolveClip(name));
  if (!available.length) return;
  const selected = available[Math.floor(Math.random() * available.length)];
  roamUntil = clock.elapsedTime + 2.5;
  roamMode = "idle";
  playClip(selected, { once: true });
}

function onPointerDown(event) {
  if (event.button !== 0) return;
  pointerDown = { x: event.clientX, y: event.clientY };
}

function onPointerUp(event) {
  if (!pointerDown || !modelRoot) return;
  const movement = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
  pointerDown = null;
  if (movement > 5) return;

  const rect = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  if (raycaster.intersectObject(modelRoot, true).length) triggerClickAction();
}

function bindControls() {
  actionSelect.addEventListener("change", () => {
    roamEnabled = false;
    roamButton.setAttribute("aria-pressed", "false");
    roamButton.textContent = "自动游走：关";
    playClip(actionSelect.value);
  });

  roamButton.addEventListener("click", () => {
    roamEnabled = !roamEnabled;
    roamButton.setAttribute("aria-pressed", String(roamEnabled));
    roamButton.textContent = `自动游走：${roamEnabled ? "开" : "关"}`;
    roamUntil = 0;
    if (!roamEnabled) playClip("idle");
  });

  resetButton.addEventListener("click", resetCamera);
  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointerup", onPointerUp);
}

function onResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight, false);
}

function disposeObject(root) {
  root.traverse?.((object) => {
    if (!object.isMesh) return;
    object.geometry?.dispose();
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.filter(Boolean).forEach((material) => {
      Object.values(material).forEach((value) => value?.isTexture && value.dispose());
      material.dispose();
    });
  });
}

function cleanup() {
  renderer.setAnimationLoop(null);
  disposableRoots.forEach(disposeObject);
  disposableTextures.forEach((texture) => texture.dispose());
  controls.dispose();
  dracoLoader.dispose();
  ktx2Loader.dispose();
  renderer.dispose();
}

async function start() {
  try {
    loadingDetail.textContent = "读取神兽设定…";
    config = await fetchConfig();
    renderMetadata();
    configureCamera();
    addLighting();
    addGround();
    addEnvironmentAccents();
    await loadBackground();
    await Promise.all([loadProps(), loadCreature()]);
    bindControls();
    roamEnabled = config.roaming?.enabled !== false;
    roamButton.setAttribute("aria-pressed", String(roamEnabled));
    roamButton.textContent = `自动游走：${roamEnabled ? "开" : "关"}`;
    loadingState.classList.add("is-hidden");
    runtimeMetrics.status = "ready";
    runtimeMetrics.started_at = performance.now();
    document.body.dataset.viewerStatus = "ready";

    renderer.setAnimationLoop(() => {
      const delta = Math.min(clock.getDelta(), 0.05);
      const elapsed = clock.elapsedTime;
      mixer?.update(delta);
      updateRoaming(delta, elapsed);
      followTarget.set(actor.position.x, 1.35, actor.position.z);
      followDelta.copy(followTarget).sub(controls.target).multiplyScalar(0.08);
      controls.target.add(followDelta);
      camera.position.add(followDelta);
      controls.update();
      renderer.render(scene, camera);
      runtimeMetrics.frames += 1;
      const seconds = Math.max(0.001, (performance.now() - runtimeMetrics.started_at) / 1000);
      runtimeMetrics.average_fps = runtimeMetrics.frames / seconds;
      runtimeMetrics.draw_calls = renderer.info.render.calls;
      runtimeMetrics.rendered_triangles = renderer.info.render.triangles;
      if (runtimeMetrics.frames % 30 === 0) {
        document.body.dataset.averageFps = runtimeMetrics.average_fps.toFixed(1);
        document.body.dataset.drawCalls = String(runtimeMetrics.draw_calls);
        document.body.dataset.renderedTriangles = String(runtimeMetrics.rendered_triangles);
      }
    });
  } catch (error) {
    console.error(error);
    loadingState.classList.add("is-hidden");
    errorMessage.textContent = error.message || "未知错误";
    errorPanel.hidden = false;
    runtimeMetrics.status = "error";
    runtimeMetrics.error = error.message || "Unknown error";
    document.body.dataset.viewerStatus = "error";
  }
}

window.addEventListener("resize", onResize);
window.addEventListener("beforeunload", cleanup, { once: true });
start();
