# Shanhai3d 资产约定

在创建或修改神兽产物前读取本文件。所有相对路径以 Shanhaiworld 项目根目录为基准。

## 工程级约定

- 根目录 `index.html` 是神兽图鉴首页，只读取 `assets/data/collections.json`。
- 每只神兽必须有独立的 `collections/<slug>/index.html`，并可通过静态服务器直接访问。
- 每只神兽页面只做轻量入口，复用 `assets/css/site.css` 和 `assets/js/collection-page.js`。
- `assets/templates/collection/` 是新页面模板。不得在每只神兽目录复制公共 JS、CSS 或 Three.js 运行逻辑。
- `<slug>` 使用小写 ASCII 字母、数字和连字符。Skill 自主选择可读拼音或常见英文，不向用户询问。
- 初始化后首页条目为 `draft`；只有参考图、模型结构、材质细节、合格运动系统、至少 6 个符合身体结构的丰富动作、交互、场景和性能全部验收通过后才能改为 `ready`。运动系统首选真实骨骼，也允许达到同等动作语义和局部形变质量的 morph、articulated node 或 hybrid 路线。

## 单只神兽标准目录

```text
collections/<slug>/
├── index.html
├── collection.json
├── preview.webp
├── spec.json
├── manifest.json
├── production/
│   ├── audit.json
│   ├── research/
│   │   └── sources.json
│   ├── prompts/
│   │   ├── concepts/
│   │   ├── views/
│   │   ├── scenes/
│   │   └── previews/
│   ├── generations/
│   │   ├── concepts/
│   │   ├── views/
│   │   ├── scenes/
│   │   └── previews/
│   ├── providers/
│   │   ├── rodin/
│   │   │   ├── tasks.json
│   │   │   ├── requests/
│   │   │   └── responses/
│   │   └── tripo/
│   │       ├── tasks.json
│   │       ├── requests/
│   │       └── responses/
│   └── logs/
├── concepts/
│   └── master.png
├── views/
│   ├── front.png
│   ├── left.png
│   ├── right.png
│   └── back.png
├── models/
│   ├── raw.glb
│   ├── rigged.glb
│   └── web.glb
├── animations/
├── scene/
│   ├── scene.json
│   ├── background.webp
│   └── props.glb
└── reports/
    ├── contact-sheet.png
    ├── reference-qc.json
    ├── model-qc.json
    ├── detail-qc.json
    ├── rig-qc.json
    ├── animation-qc.json
    └── report.json
```

允许使用 `raw-v2.glb` 等版本化文件，禁止静默覆盖已标记为 `ready` 的文件。

## 生产过程与可追溯性

`production/` 保存完整生产证据，不是临时缓存。不得只保存最终选中的图片。

- 每次考据结果写入 `production/research/sources.json`，保留来源、访问时间和采用的原典特征。
- 每次 ImageGen 调用前，先把实际 Prompt、负面约束、参考图路径和预期输出写入一个编号 JSON，例如 `production/prompts/concepts/001-master.json`。
- 每轮生成图原样保存在 `production/generations/` 对应阶段，采用 `001-*`、`002-*` 递增编号；失败或未选中的图也保留。
- 最终选中图复制或转换到 `concepts/master.png`、`views/*.png`、`scene/background.webp`、`preview.webp` 等稳定交付路径；选择理由和源文件路径写入 `production/audit.json.selections`。
- Rodin/Tripo 的脱敏请求、响应摘要和 task ID 分别保存在各自 `production/providers/<provider>/requests/`、`responses/` 和 `tasks.json`。
- 不覆盖旧 Prompt 或旧生成图。重试必须新建编号文件，并在 `audit.json.runs` 追加一条记录。

单次图片生成 Prompt 记录示例：

```json
{
  "schema_version": 1,
  "id": "concept-001",
  "stage": "concept",
  "tool": "codex_imagegen",
  "created_at": "2026-08-14T00:00:00+00:00",
  "prompt": "实际提交的完整 Prompt",
  "negative_prompt": "实际使用的负面约束",
  "references": [],
  "outputs": [
    "collections/jiuweihu/production/generations/concepts/001-master.png"
  ],
  "status": "selected",
  "notes": []
}
```

`production/audit.json.runs` 的每条记录至少包含 `id`、`stage`、`tool`、`created_at`、`prompt_files`、`reference_files`、`output_files`、`status` 和 `notes`。文件路径统一以项目根目录为基准，便于脚本核对。

## collections.json

首页目录位于 `assets/data/collections.json`：

```json
{
  "schema_version": 1,
  "collections": [
    {
      "id": "jiuweihu",
      "name": "九尾狐",
      "subtitle": "青丘异兽",
      "summary": "九尾灵狐，声如婴儿。",
      "body_type": "quadruped",
      "preview": "./collections/jiuweihu/preview.webp",
      "href": "./collections/jiuweihu/index.html",
      "status": "ready"
    }
  ]
}
```

首页只展示 `status: "ready"` 的条目。预览图使用最终定稿概念图或 3D 实机画面裁成 WebP，不使用临时占位图发布。

## collection.json

神兽页面的唯一差异化运行配置。至少包含：

```json
{
  "schema_version": 1,
  "id": "jiuweihu",
  "name": "九尾狐",
  "status": "ready",
  "preview": "./preview.webp",
  "model": {
    "path": "./models/web.glb",
    "target_height": 2.6,
    "facing_offset": 0,
    "in_place_root_motion": true
  },
  "animation": {
    "mode": "skeletal",
    "min_actions": 6,
    "min_animated_nodes": 3
  },
  "scene": {
    "background": "./scene/background.webp",
    "background_color": "#0b1110",
    "fog_color": "#0d1515",
    "fog_near": 14,
    "fog_far": 46,
    "ground_color": "#18221f",
    "ground_size": 42,
    "props": "./scene/props.glb"
  },
  "actions": {
    "idle": ["Idle", "Idle_2"],
    "walk": ["Walk"],
    "run": ["Run"],
    "click": ["Roar", "Attack"]
  },
  "roaming": {
    "enabled": true,
    "bounds": 5.5,
    "walk_speed": 0.75,
    "run_speed": 1.55
  },
  "facts": []
}
```

动作名必须来自 GLB 实际 clips；配置可以提供同义候选，但不能声称不存在的动作已生成。

## spec.json

保留以下语义：

```json
{
  "schema_version": 1,
  "creature_id": "jiuweihu",
  "name": "九尾狐",
  "status": "initialized",
  "source": {
    "canonical_traits": [],
    "visual_inferences": [],
    "citations": []
  },
  "design": {
    "body_type": "quadruped",
    "locked_traits": [],
    "anatomy_profile": {
      "counted_features": [],
      "continuous_features": [],
      "articulated_regions": [],
      "surface_features": [],
      "locomotion_modes": [],
      "not_applicable": []
    },
    "palette": [],
    "animations": []
  },
  "scene": {
    "habitat": "",
    "terrain": "",
    "time_of_day": "",
    "weather": "",
    "palette": [],
    "lighting": {},
    "props": []
  }
}
```

`canonical_traits` 只存可追溯特征；为了画面补全的颜色、纹样、材质和装饰进入 `visual_inferences`。

## manifest.json

把它当作可恢复的流水线状态，不当作宣传文案。单个 artifact 建议字段：

```json
{
  "kind": "web_glb",
  "path": "collections/jiuweihu/models/web.glb",
  "status": "ready",
  "sha256": "...",
  "notes": []
}
```

状态只使用：

- `pending`：尚未开始。
- `running`：任务正在执行。
- `needs_review`：产物存在，等待质量确认。
- `ready`：已验证通过。
- `failed`：任务失败，记录原因。
- `blocked_credentials`：缺少本地密钥。
- `blocked_provider`：服务商当前不支持或不可用。
- `blocked_reference_quality`：参考图不满足该生物 anatomy profile 中适用的数量、连续结构、连接关系或跨视图一致性。
- `blocked_model_quality`：3D 结构、拓扑或连接关系失败。
- `blocked_detail_quality`：关键毛发、鳞片、羽毛、面部或材质细节失败。
- `blocked_rig_quality`：首选骨骼路线没有有效 skin/weights 或覆盖不足，且替代运动路线仍在评估；这不是用整体摇晃发布的理由。
- `blocked_motion_quality`：骨骼与所有合理替代运动系统都无法覆盖主要活动区域或保持合格局部形变。
- `blocked_animation_quality`：所有已选运动路线仍少于 6 个合格动作，或动作语义、局部形变、节奏与过渡不合格。

## 结构验收

把以下检查写入 `checks`：

- `canonical_trait_match`
- `anatomy_profile_defined`
- `counted_features_if_applicable`
- `continuous_structure_integrity`
- `articulated_region_coverage`
- `view_consistency`
- `provider_input_suitability`
- `glb_parse`
- `model_topology_and_connections`
- `closeup_detail_retention`
- `fur_or_surface_material_quality`
- `material_texture_load`
- `motion_mode_declared`
- `skeletal_attempt_recorded`
- `motion_targets_present`
- `motion_region_coverage`
- `animation_clips_present`
- `animation_variety`
- `animation_deformation`
- `animation_semantic_match`
- `threejs_desktop_interaction`
- `roaming_state_machine`
- `scene_style_coherence`
- `background_seam`
- `lighting_match`
- `ground_contact`
- `performance_budget`
- `pc_1080p_performance`
- `console_errors`
- `production_traceability`

每个检查包含 `status`、`checked_at`、`evidence` 和 `notes`。只有 evidence 可复查时才标记通过。

## 网页交付最低标准

- `collections/<slug>/index.html` 引用项目公共样式和公共查看器，不包含重复实现。
- 页面可加载 `models/web.glb`，失败时有可读错误。
- 鼠标可旋转和缩放。
- 点击模型不误触拖拽；需要部位交互时保存命中对象名称。
- 页面按 `animation.mode` 验证 skin/weights、morph targets、articulated nodes 或 hybrid 证据；声明与实际不一致时明确报错，不得整体摇晃降级。
- 动画列表来自实际可播放动作，不硬编码不存在的动作；发布版本至少有 6 个通过检查、能驱动有语义身体区域的动作。
- 支持动作交叉淡化、自动演示和手动动作选择。
- 自动游走能在有限场地内移动和转向，并同步播放与运动方式匹配的 locomotion 身体动作；不瞬移、不越界、不叠加双倍 root motion。
- 点击神兽能触发合适动作，并能区分拖拽与点击。
- 背景、地面、雾效、道具和灯光来自该神兽的 `collection.json` 与 `scene/scene.json`。
- 背景不含明显水平接缝、现代物件、文字或水印，不遮挡神兽轮廓和移动路线。
- 只按 PC 1920×1080 验收，像素比上限 2，并记录平均 FPS、总三角面和 draw calls。
- 页面离开时正确释放纹理、材质、几何体和动画资源。
- 根首页卡片可点击进入该神兽独立页面。
- 产物不引用开发者电脑的绝对路径。

## 安全约定

- 根目录允许使用 `.env`，但它必须被 Git 忽略、只能由本地脚本读取，且不能进入 `assets/`、`collections/` 或浏览器响应。
- 临时下载 URL 只用于即时下载；manifest 和 `production/` 仅保存 provider task ID、本地文件路径和脱敏摘要。
- Provider status 所需 subscription token/JWT 只能暂存在被忽略的 `.agents/runtime/`，权限 0600，任务结束立即删除；不得写入 `production/`。
- Provider 请求与响应在落盘前删除密钥、Authorization header、Cookie、签名参数、账户信息和计费信息。
- 原始 Prompt 与中间图片必须保留；包含秘密或临时授权信息的原始网络响应不得保留。
