# Shanhaiworld project rules

## Product contract

- Treat one Chinese mythic-creature name as the complete input and use the repo-scoped `$shanhai3d` skill.
- Do not ask the user for prompts, images, style, action names, scene design, performance targets, or Blender work.
- Deliver one independent PC Three.js page with coherent environment, mouse orbit/zoom/click, autonomous roaming, high-fidelity materials, and rich anatomically meaningful motion. Prefer a real skeleton; accept morph, articulated-node, mesh-deformation, or hybrid motion only when it meets the same visible quality bar.
- Keep the viewer shell collection-invariant. Every collection, including newly initialized ones, must use `viewer_ui: "shared-v1"`, `kid_mode: true`, `narration.voice_profile: "mandarin-tingting-r160-v1"`, a fixed versioned narration audio file, the shared template, `assets/js/collection-page.js`, and `assets/css/site.css`. The shared controls include top-right previous/next creature links derived from ready catalog order; the first collection disables previous and the last disables next. They also include the immersive-mode toggle, which hides all nonessential overlays while preserving a clear exit control and Escape-key exit. Do not create creature-specific UI, control, interaction, narration voice/rate, or layout variants; only creature content, model, actions, camera, lighting, and scene may differ. Browser speech synthesis is not an acceptable release fallback. A mismatched ready collection must fail the site build.
- Keep every release scene readable through a full actor turn: use key, fill and rim lights plus environment illumination when an equirectangular scene is present. At the normal camera distance, face, appendage connections, silhouette and material relief must remain legible at all eight 45-degree yaw samples; a dramatic dark background cannot substitute for readable subject lighting.
- Keep scene rotation collection-invariant. Every ready collection and every newly initialized collection must use a native 2:1 equirectangular environment for `scene.background`, set `background_mode: "equirectangular"`, and allow unlimited OrbitControls azimuth. A fixed rectilinear screen plate, a stretched 16:9 image, a cubemap cross, or a panorama with a visible left/right seam fails release. Persist at least four browser orbit checkpoints plus an edge/seam check.
- Automation never overrides quality gates. Stop with an explicit blocking status instead of publishing a structurally wrong, blurry, unrigged, or weakly animated result.

## Mandatory stage gates

Complete and persist each gate before starting the next paid stage. Read `.agents/skills/shanhai3d/references/quality-gates.md` for the full checklist.

### Reference images

- Separate the cinematic identity master from clean provider input views.
- Provider views must use one frozen pose, matching proportions/materials, neutral light, a clean contrasting background, and consistent orthographic directions.
- Build a creature-specific `anatomy_profile` before prompting: counted features, continuous structures, articulated regions, surface features, locomotion modes, and explicit not-applicable items. Validate only applicable counts; validate continuous bodies by silhouette, volume, connection, and branch topology; validate moving regions by attachment and available motion space.
- Do not treat `exactly N` in the prompt as evidence. Do not submit mirrored images as genuine opposite views.
- Save `reports/reference-qc.json`. If any blocking check fails, regenerate the earliest bad view and do not call the 3D provider.

### Model structure and detail

- Submit only the 2–4 views that passed QC; more inconsistent views are worse than fewer consistent views.
- Validate the high-quality source model with eight-direction turntable renders and close-ups before remeshing, rigging, or optimization.
- Reject any mismatch with the anatomy profile, fused or floating geometry, broken connections, topology holes, blurry identity features, smooth clay/plastic surfaces, or unreadable PBR detail.
- Never ship a model whose wrong anatomy was repaired by deleting erroneous generated parts. BANG/component splitting is not an anatomy-correction workflow.
- Apply detail rules conditionally: fur needs silhouette clumps plus directional normal/roughness; scales, plates, feathers, skin and keratin each need their own readable geometry/normal, overlap and reflectance cues. Preserve identity regions and silhouette during optimization.
- Persist `reports/model-qc.json` and `reports/detail-qc.json` before rigging.

### Motion system and animation

- Run provider `rig-check` and use a currently documented rig type matching the creature body type; never force a non-humanoid asset onto a biped skeleton.
- For the preferred skeletal route, the final GLB must contain a skin, valid joint/weight attributes, and chains covering the creature's `articulated_regions`.
- If a provider cannot rig the body type to release quality, document that attempt and use morph targets, articulated nodes, deterministic mesh deformation, or a hybrid. The fallback must drive meaningful local regions, preserve connections, and remain auditable; a whole-model wobble is never a fallback.
- Final release requires at least six validated actions: idle, a locomotion matching `locomotion_modes`, and four distinct action/reaction/signature motions chosen for the creature.
- Each action needs preparation, main and recovery phases, and must affect at least two semantic body regions or one continuous body-length deformation field. Translation, rotation or scale of the actor root, camera motion, materials and particles do not fill action slots.
- Validate motion by visible behavior, not clip count or channel presence. A signature/attack/reaction peak should move its primary end effector or silhouette by at least 8% of the on-screen creature span, while locomotion contact or propulsion regions should show at least 4%, unless anatomy makes that threshold unsafe and the report records a justified equivalent. Feet, wings, fins or body waves must visibly explain contact or propulsion; subtle wobble, sliding and renamed near-identical clips fail.
- Code-authored motion may target joints, morph weights, articulated nodes or reproducible mesh deformation. Bake tracks into the GLB when possible; otherwise keep deterministic animation assets with the collection and apply the same visual QA.
- Persist `reports/rig-qc.json` and `reports/animation-qc.json`. Fewer than six actions, semantic mismatch, root-only motion, sliding, collapse, detachment, visible seams or unstable deformation block release.

## Provider boundaries

- Use Rodin for the high-quality static source model; do not imply it supplies the required non-humanoid rig and rich animation set.
- For non-humanoid rigging, verify current Tripo docs, call `rig-check`, and use the documented non-humanoid model/rig type.
- Tripo non-humanoid preset animation coverage may be sparse; never describe one locomotion preset as a rich action set.
- Meshy API rigging is not a non-humanoid fallback unless current official API docs explicitly support the target body type. Web-app features do not prove API support.
- Require `RODIN_API_KEY` and `TRIPO_API_KEY` for the default complete pipeline. ImageGen does not use `OPENAI_API_KEY`.
- Quality outranks credits and paid attempt count. Never lower source topology, texture resolution, action richness or gate thresholds to save credits. Retry only after diagnosing a failure and changing a relevant input, parameter, topology, source or provider.

## Repository shape and traceability

```text
index.html
assets/
collections/<slug>/index.html
collections/<slug>/collection.json
collections/<slug>/preview.webp
collections/<slug>/{concepts,views,models,animations,scene,reports}/
collections/<slug>/production/{research,prompts,generations,providers,logs}/
```

- Reuse shared loaders, UI, animation state, roaming logic and CSS under `assets/`; generate collection HTML from `assets/templates/collection/index.html`.
- Keep paths relative. Preserve every prompt, selection/rejection decision and sanitized provider task. Preserve binary evidence by unique content, not by every temporary path: one SHA-256 value gets one canonical committed file.
- Never overwrite accepted assets; create versioned replacements and append audit records.
- Keep collection and catalog status `draft` until every mandatory gate passes. Only `ready` collections appear on the home page.

### Artifact hygiene and admission gate

- Treat `production/` as an audit trail, not a download cache. Keep text records complete; commit only binary artifacts that are selected inputs/outputs, materially distinct rejected evidence needed to explain a gate, deterministic reproduction inputs, final runtime assets, or the minimum QC media explicitly referenced by a report.
- Never commit byte-identical binaries at multiple paths. A stable delivery path may itself be the canonical original; record its provider task, source role, SHA-256 and byte size instead of copying it into `production/`. Do not keep `models/web-vN.glb` when it is identical to `models/web.glb` or duplicate provider downloads under both `production/providers/**` and `models/**`.
- Download provider outputs and disposable renders into ignored `.agents/runtime/<slug>/`. Promote only a reviewed unique artifact to a versioned canonical path such as `models/raw-vN.glb` or `models/rigged-vN.glb`; update provider/audit JSON to that path and remove the temporary download when the task ends.
- Do not commit provider archives, raw download directories, caches, contact sheets superseded by a final sheet, exploratory screenshots, duplicate close-ups, or unreferenced browser captures. Every committed binary under a collection must be referenced by `collection.json`, `manifest.json`, `production/audit.json`, or a QC report.
- Failed or superseded large binaries are not automatically production evidence. Keep their prompt, provider task, rejection reason, SHA-256 and byte size; retain the binary only when it is materially distinct and necessary for reproducibility or gate review. Otherwise use approved external artifact storage or leave it untracked locally—never invent a permanent URL and never commit an expiring signed URL.
- Before any asset commit, stage explicit paths and run `python3 .agents/skills/shanhai3d/scripts/audit_assets.py --project-root . --staged`. Any duplicate, orphaned binary, provider-download binary, oversized normal-Git object or unapproved archive blocks the commit. Also inspect `git diff --cached --stat`, `git check-attr -a <asset>` and `git lfs ls-files`.

## Git commit convention

- Create commits only when the user explicitly asks. Do not push, amend, rebase, squash, tag, or rewrite existing history without separate authorization.
- Use Conventional Commits: `<type>(<scope>): <summary>`. Keep the summary imperative, specific, and at most 72 characters; use either Chinese or English consistently within one commit.
- Allowed types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, and `revert`.
- Prefer a concrete scope such as `skill`, `pipeline`, `viewer`, `scene`, `assets`, `home`, or the creature slug. Examples:
  - `feat(jiuweihu): add verified animated collection`
  - `fix(viewer): reject root-only motion as an action`
  - `docs(skill): generalize anatomy quality gates`
- Keep each commit atomic: one behavior change, one infrastructure change, or one creature production milestone. Do not mix unrelated refactors, documentation edits, generated assets, and creature work in a single catch-all commit.
- A creature milestone must commit its code/config together with the prompts, selected unique source artifacts, sanitized provider task records, audit updates, and the minimum QC evidence needed to reproduce and review it. Rejected binaries may be included only when materially distinct and explicitly referenced; rejection metadata alone is sufficient for redundant or externally stored artifacts. Never include raw secrets or unsanitized responses.
- Do not mark a collection `ready` or commit its catalog promotion until all mandatory gates pass. Prefer a separate final commit for the `draft` → `ready` promotion so the release decision is reviewable.
- Before committing, inspect the complete diff and run the checks relevant to the changed files. Never bypass failing hooks or validation with `--no-verify`.
- Never commit `.env`, API keys, Authorization/Cookie values, provider JWTs, signed URLs, account/billing data, `.agents/runtime/`, temporary downloads, caches, or local server output. Confirm provider records are sanitized before staging them.
- Preserve user-authored or unrelated working-tree changes. Stage explicit paths instead of `git add .` when unrelated files are present.
- Do not introduce Git LFS, rewrite binary history, or remove versioned production evidence solely to reduce repository size unless the user explicitly approves that repository-level change.

### Large files and Git LFS

- Follow the repository `.gitattributes`; do not broaden LFS to every `*.png`, `*.webp`, or `*.glb` without explicit approval. Small runtime assets should not pay the collaboration and hosting cost of LFS unnecessarily.
- Use normal Git for text, prompts, audit/QC JSON, code, small previews, and optimized runtime assets below 10 MiB.
- Prefer LFS for binary source assets from 10–50 MiB when they are expected to change, including source/intermediate GLB files, animation binaries, high-resolution concepts/views, and original generated images.
- Files at or above 50 MiB must not enter normal Git. Put them in LFS or approved external object storage before staging. GitHub rejects normal Git objects above 100 MiB, so 100 MiB is a hard failure threshold, not the point at which cleanup should begin.
- Prefer external object/artifact storage for a single file above 500 MiB, provider archives, caches, or large batches of failed generations. Keep a sanitized URL/object key, SHA-256, size, provenance, and selection status in the collection audit; do not commit expiring signed URLs.
- `collections/<slug>/models/web.glb`, `preview.webp`, optimized scene backgrounds, and other files required directly by the static page remain normal Git assets only while each is below 50 MiB. If a runtime asset reaches that threshold, optimize it or decide the hosting/CDN strategy with the user instead of silently moving it to LFS.
- GitHub Pages cannot serve Git LFS objects as ordinary site assets. When Pages is the target, keep compliant optimized runtime files in normal Git or deploy them to an external static host/CDN; use LFS only for production/source assets that the page does not request directly.
- LFS stores each version of a binary as a new object. Do not repeatedly commit tiny changes to huge models; finish a meaningful production milestone locally, then commit the reviewed version and its traceability records.
- Before committing assets, run the artifact admission gate, inspect file sizes and verify the intended classification with `git check-attr -a <path>` and `git lfs ls-files`. A file represented by an LFS pointer must have its corresponding LFS object available.
- Adding LFS rules before the first asset commit is safe. Migrating already committed files or rewriting history with `git lfs migrate` requires explicit user approval and a backup/coordination plan.

## Three.js requirements

- Load `models/web.glb` and validate the declared `animation.mode`: skeletal needs a skinned mesh, morph needs morph-target tracks, articulated needs multiple animated semantic nodes, and hybrid needs valid evidence from its component modes.
- Populate controls only from real playable actions; crossfade or equivalently blend actions and keep locomotion in place.
- Autonomous world movement must be paired with a locomotion action that visibly expresses the expected gait, flap, wave, crawl or swim. World movement controls the path, not body motion.
- Keep props out of creature raycasts, distinguish click from drag, constrain orbit/zoom, follow a roaming actor, and release all GPU resources.
- Validate at 1920×1080 near 60 FPS, but do not trade away recognizable fur, facial, appendage or deformation quality merely to hit a smaller file.

## Validation and security

- Run `inspect_glb.py models/web.glb --motion-mode <skeletal|morph|articulated|hybrid> --min-animations 6`, then validate every action visually in the browser.
- Record triangle count, texture sizes/channels, joint count, clips, animated nodes, draw calls, FPS, load size, console errors and close-up comparisons.
- Load keys through `env_utils.py`; process values override root `.env`.
- Never expose `.env`, `.agents` or `production/` from the preview server.
- Never write or echo provider keys, Authorization, Cookie, account/billing data, subscription JWTs or signed download URLs. Store active status tokens only in ignored `.agents/runtime/` with mode 0600 and delete them when the task ends.
