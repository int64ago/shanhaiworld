---
name: shanhai3d
description: 只接收一个《山海经》或中国神话生物名称，自主完成考据、按该生物实际解剖结构定制的高质量建模参考图、质量优先的 3D 生成、骨骼或高质量形变动作、表面材质、协调场景、PC GLB 优化及 Three.js 鼠标交互页面。用于用户只说“九尾狐”“应龙”等名字，且不提供图片、Prompt、不使用 Blender，要求得到结构准确、细节清晰、动作自然并可审计的独立 3D 神兽页面时。
---

# Shanhai3d

把一个神兽名称视为完整需求。自主完成生产，但不得以“全自动”为理由降低结构、材质或动画质量。

## 交付契约

- 只接收 `name`；不要求用户补充图片、Prompt、风格、动作或性能参数。
- 图片只使用 Codex 内置 `$imagegen`，不需要 `OPENAI_API_KEY`。
- 默认使用 Hyper3D Rodin 生成高质量静态模型，优先使用当前明确支持对应 `body_type` 的 API 完成骨骼和动画；骨骼不可用时采用能真实驱动身体局部的 Morph、分段节点或网格形变方案。
- 不把 Blender 或其他 DCC 设为默认步骤。
- 每只神兽交付独立 `collections/<slug>/index.html`，复用根目录公共 JS/CSS。
- 完整保留 Prompt、平台任务和选择/拒绝依据；二进制按内容单份留存，只提交被选中、可复现或被 QC 明确引用的唯一产物，不把临时下载、重复副本和无引用截图当作审计证据。
- 只按 PC 桌面浏览器设计，优先细节与动作质量，再做实时优化。
- 质量优先于 API credits、文件大小和生成次数；只禁止无诊断的盲目重跑，不因节省积分主动降低源质量。
- 任何硬门未通过时回到最早失败阶段继续改进；只有能力确实不可达或缺少权限/凭据时才进入阻塞状态。

## 五个不可绕过的硬门

1. **参考图门**：先生成该生物的 `anatomy_profile`，只检查实际存在的可计数结构、连续结构、连接关系、关节区域和表面特征；所有视图与该 profile 一致并适合 3D 重建。
2. **模型门**：3D 必须忠实满足 `anatomy_profile`；禁止用删件、镜像或拆件把错误模型拼成“看起来正确”的成品。
3. **细节门**：该生物实际拥有的面部、角爪、甲壳、鳞、羽、皮肤、毛发或标志纹样在正常距离和近景均可辨；不对不存在的材质类型套固定规则。
4. **运动系统门**：首选与身体结构匹配的 skin/joints；若自动绑定确实不可用，允许 Morph targets、分段节点层级或程序网格形变，但必须驱动实际身体局部并可审计。
5. **动作门**：最终至少有 6 个经浏览器验证、语义明确且接近预期行为的动作，包含待机、主要移动和特色/反应动作。仅移动、旋转、缩放或上下晃动整个模型不算动作。

执行图片、模型、骨骼或动画阶段前，完整读取 [quality-gates.md](references/quality-gates.md)。创建或修改产物前读取 [artifact-contract.md](references/artifact-contract.md)，遵守其中的单份二进制与提交准入规则。调用平台前读取 [provider-workflow.md](references/provider-workflow.md) 并核对当前官方文档。

## 快速入口

```bash
python3 .agents/skills/shanhai3d/scripts/init_creature.py "九尾狐" --slug jiuweihu --project-root .
python3 .agents/skills/shanhai3d/scripts/check_environment.py --project-root . --strict
```

默认完整路线需要：

- `RODIN_API_KEY`：高质量 3D 生成。
- `TRIPO_API_KEY`：非人形 rig-check、绑定和骨骼动画。
- `MESHY_API_KEY`：仅在当前官方 API 明确支持目标身体类型时作为备选。

密钥只从进程环境或根目录 `.env` 读取，不回显、不进入浏览器或生产记录。

## 工作流

### 1. 初始化、恢复与考据

1. 自主选择可读 ASCII slug，运行初始化脚本。
2. 读取 `spec.json`、`manifest.json` 和已有审计，从最后一个未完成阶段继续。
3. 搜索原典和权威来源，把事实写入 `canonical_traits`，把色彩、纹样、材质等发挥写入 `visual_inferences`。
4. 生成 `design.anatomy_profile`：按该生物实际情况记录 `counted_features`、`continuous_features`、`articulated_regions`、`surface_features`、`locomotion_modes` 和明确不适用项；不预设它一定有尾、翼、足或毛发。
5. 写入 `production/research/sources.json`，不得把影视或游戏二创冒充原典。

### 2. 分开生成视觉主稿与建模输入图

1. 先生成用于审美和材质锁定的三分之四视觉主稿，再生成专供 3D 平台使用的正交建模图；两者用途不可混淆。
2. 每次生成前记录完整 Prompt、负面约束、参考路径和预期输出；保存每轮原图。
3. 建模图使用同一个冻结姿势、比例、镜头、材质和中性照明。背景用与主体明度分离的纯色，不使用场景、雾、强轮廓光、景深或投影干扰。
4. 依据 `anatomy_profile` 动态生成约束：可计数结构要边界清楚且数量正确；连续结构要轮廓和连接连续；需要独立活动的区域要看清连接、活动范围与遮挡关系。不存在的结构标记 `not_applicable`，不得套用尾巴或四足规则。
5. 用主稿作为唯一角色参考派生视图，但不要把镜像图冒充真实相反侧视图。某个视图不一致时宁可不提交，也不要为了凑四张污染多视图条件。
6. 主代理逐张以原始分辨率检查，并在 200% 近景核对关键结构与材质。Prompt 中写了 “exactly N” 不是通过证据。
7. 把结果写入 `reports/reference-qc.json`。所有适用阻断项通过后才复制到稳定路径并进入 3D；失败后针对根因迭代，不设基于积分的固定重试次数。

### 3. 生成高质量源模型

1. 只提交通过参考图门的 2–4 张互相一致图；不盲目追求视图数量。
2. 先生成高质量源模型，再优化网页版本。项目 Rodin 客户端默认 `Quad + high + 4K HighPack`；只按最终视觉证据决定是否调整，不为节省 credits 主动降档。
3. 下载后生成 8 方位转台图，以及 `anatomy_profile` 中关键结构和材质的近景图。逐项核对数量或连续性、连接、破面、融合、悬浮和贴图清晰度。
4. 错误来自参考图时回到图片阶段；3D 重建错误时改变输入、Prompt、参数或 provider 后继续迭代。禁止用删掉错误生成结构的方式伪装正确模型。
5. 把结果写入 `reports/model-qc.json`。未通过则保持 `blocked_model_quality`，不进入绑定。

### 4. 保住该神兽实际拥有的表面与材质细节

1. 从 `surface_features` 选择适用策略：毛发使用分层毛束和方向性 normal/roughness；鳞片、羽毛、甲壳、湿润皮肤、石质或金属质分别使用匹配的几何与 PBR 表达。
2. 源纹理优先 4K PBR；最终网页纹理按近景对比结果选择 2K/4K 与 KTX2，不先用文件大小决定质量。
3. 优先保留 `anatomy_profile` 标记的身份关键区、轮廓转折和标志纹样；不得为了减面抹平关键结构或表面层次。
4. 在相同镜头和灯光下保存压缩前后近景对比。任何关键细节明显退化都回退优化参数。
5. 把结果写入 `reports/detail-qc.json`；未通过则标记 `blocked_detail_quality`。

### 5. 选择并实现高质量运动系统

1. 骨骼仍是首选。先调用 `rig-check`，再使用与 `body_type` 匹配的 rig 类型；不得给非人形强套双足骨架。
   使用 `scripts/tripo_client.py` 完成 `upload → rig-check → poll → rig → poll → retarget → poll → download`，所有记录自动脱敏。
2. 绑定后用 `inspect_glb.py --require-skin` 验证 skin、joint、权重和骨骼层级，并实际转动关键关节观察变形。
3. 按 `articulated_regions` 验证关节覆盖与权重；不同身体类型使用各自的解剖链，不强制固定骨骼清单。
4. 若多轮绑定、替代 provider 和代码绑定仍不能得到可靠 skin，选择 `morph_targets`、`articulated_nodes` 或 `mesh_deformation`。降级方案必须在 GLB 中保存可播放 tracks，至少驱动多个语义相关身体区域并产生清楚的轮廓/姿态变化。
5. 最终至少提供 6 个动作：待机、该生物的主要 locomotion，以及不少于 4 个观察、转向、攻击、防御、鸣叫、受击、跳跃、飞行、游泳、盘绕或特色展示动作。动作集合按身体结构和传说能力自行选择。
6. 每个动作都要有准备、主体和恢复阶段；移动动作必须有与位移匹配的步态、振翅、摆尾、蛇形波动或游动形变。世界位移只负责路径，不能充当身体动作。
7. 验证节奏、重心、接触、穿模、形变、循环和切换。骨骼方案用交叉淡化；Morph/节点/网格方案使用等价的平滑混合。
8. 把 `motion_mode`、动作语义、实际驱动区域和浏览器证据写入 `reports/rig-qc.json` 与 `reports/animation-qc.json`。非骨骼方案必须明确披露，但动作质量通过时可发布。

### 6. 优化 PC 网页模型

1. 保留 `models/raw.glb` 与 `models/rigged.glb`，另生成 `models/web.glb`。
2. 以 1920×1080 单主角为基准，网页模型从约 200k–350k 三角面、关键 4K PBR、材质不超过 10 个开始；根据实测调整，不设移动端预算。
3. 使用 Meshopt/Draco 和 KTX2 时，确认 Three.js 解码器可用，并确保当前 `motion_mode` 所需的 skin/weights、Morph targets、节点层级和 animation tracks 未被优化掉。
4. 比较源模型与网页模型的轮廓、近景材质和动作形变；只有视觉与动作都保真才通过。

### 7. 场景与 Three.js 页面

1. 根据出处生成协调的 2:1 远景或程序环境；降低背景对比和细节密度，使主体清楚落地。
2. 页面使用 `GLTFLoader`、`OrbitControls`、raycaster 和 `AnimationMixer`；动作菜单只列出真实 GLB clips，clip 可以驱动 joints、Morph weights 或分段节点。
3. 自动游走必须同时播放对应 locomotion 形变；世界位移只负责路径移动，不得替代身体运动。
4. 点击触发与语义匹配的真实形变动作，区分拖拽与点击；支持平滑混合、相机跟随、边界转向和资源释放。
5. 模型既没有可靠 skin，也没有可验证的 Morph/分段节点/网格形变 clips 时页面明确报错；不启用整体摇晃降级。

### 8. 验收与发布

1. 运行：

   ```bash
   python3 .agents/skills/shanhai3d/scripts/inspect_glb.py collections/<slug>/models/web.glb --motion-mode <skeletal|morph|articulated|hybrid> --min-animations 6
   ```

2. 在 PC Chrome 1920×1080 检查首页入口、GLB/贴图、所有动作、鼠标旋转缩放、点击、游走、背景接缝、接地、控制台和资源释放。
3. 保存结构、材质与毛发近景，以及每个动作的可复查截图或短视频证据；记录三角面、纹理、draw calls、FPS 和加载体积。
4. 删除或外置未被审计/QC 引用的临时产物，确保同一 SHA-256 只保留一个规范文件；provider 下载不得同时存在于 `production/providers/**` 与 `models/**`。
5. 对准备提交的显式路径运行：

   ```bash
   python3 .agents/skills/shanhai3d/scripts/audit_assets.py --project-root . --staged
   ```

   重复二进制、孤立二进制、provider 下载目录、超限普通 Git 对象或未批准归档任一存在时不得提交。
6. 只有参考图、模型、细节、运动系统、动画、场景、交互、性能、审计与资产准入全部通过，才把 collection 与 catalog 同时改为 `ready`。

## 失败与费用规则

- 参考图门未通过时禁止调用 Rodin；模型门未通过时禁止调用 rig/animation。
- 不设置基于 credits 的固定重试上限；每次失败必须先诊断并改变输入、Prompt、参数、拓扑或 provider，禁止相同条件下盲目烧调用。
- 缺少 Rodin 或 rig provider 的必要密钥时保留已完成的免费阶段，标记 `blocked_credentials`。
- Provider 当前不支持骨骼时继续尝试可审计的 Morph、分段节点或网格形变路线；只有所有可行运动路线都无法达到动作语义和质量门时才标记 `blocked_provider`。
- 永远不保存密钥、Authorization、Cookie、账户信息、轮询令牌或临时签名 URL。
