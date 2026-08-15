# Provider 工作流参考

在首次实时 API 调用、修改 provider 客户端或排查失败前读取。接口和能力会变化；每次实际调用前打开当前官方文档核对字段、模型版本、身体类型、动作列表与计费，不只依赖本摘要。

本参考最后核对日期：2026-08-15。

## 图片阶段：Codex 内置 ImageGen

用途：生成视觉主稿和专供 3D 重建的干净建模输入图。

- 显式使用 `$imagegen`；不读取、不检查、不索取外部 OpenAI API 密钥。
- 视觉主稿与 provider 输入图分开生成。前者锁定审美，后者优先结构清晰、负空间和跨视图一致性。
- 以一张通过检查的主稿为角色参考派生视图，不用互不关联的纯文本请求制造四个不同角色。
- 不把镜像图当作真实相反侧视图提交给 3D provider。
- 每轮调用前记录实际 Prompt；被选中、参与 QC 或能证明关键拒绝结论的唯一原图进入规范路径，其余版本记录生成 ID、SHA-256、字节数和拒绝原因，不制造相同字节副本。
- 完整执行 `quality-gates.md` 的参考图门。未通过时禁止进入付费 3D。

## 静态模型：Hyper3D Rodin Gen-2

用途：把已经通过质量门的单体多视图生成高质量 PBR GLB。不要假设 Rodin 同时提供符合要求的非人形绑定或丰富骨骼动画。

- Gen-2：https://developer.hyper3d.ai/api-specification/rodin-generation-gen2
- 状态：https://developer.hyper3d.ai/api-specification/check-status
- 下载：https://developer.hyper3d.ai/api-specification/download-results
- BANG：https://developer.hyper3d.ai/api-specification/bang
- 密钥：`RODIN_API_KEY`，只从进程环境或项目根目录 `.env` 读取。

### 输入与质量规则

- 多视图使用当前文档支持的组合模式；只提交 2–4 张全部通过 `reference-qc.json` 的一致视图。
- 第一张使用最能稳定身份与材质的结构视图。视图数量不是越多越好；一张矛盾视图会污染整体重建。
- 项目客户端默认使用 `Quad + high + HighPack`，取得适合后续动画制作的高质量拓扑和 4K PBR 源纹理。是否调整参数只由最终视觉与拓扑证据决定，不以 credits、调用次数或余额为降质理由；`--standard-textures` 仅在同镜头对比证明不会损失所需细节时使用。
- HighPack 源网格可能远高于网页预算；先验收和制作保细节的 rig 输入版本，再单独优化最终网页版本。
- 模型 Prompt 从 `anatomy_profile` 动态强调 exact anatomy、连续结构、清晰连接/关节区域和实际 surface features；只有生物确实有毛发或重复附肢时才加入对应毛束或分离约束。
- 每次生成后先转台和近景验收，结构/毛发/材质通过后才允许绑定。
- 与 anatomy profile 不符的结构必须回到参考图或重建阶段。BANG 不能作为删除错误组件、掩盖连接问题或凑结构数量的发布路线。

### 记录与临时令牌

- 提交前保存脱敏请求摘要；返回后只把 task UUID、job UUID、状态、调用次数和本地产物路径写入 `production/providers/rodin/`。
- 把下载目录设为 `.agents/runtime/<slug>/downloads/rodin/<task-id>/`。通过模型门后只将选中的唯一 GLB 提升为 `models/raw-vN.glb`，并把规范路径、SHA-256、字节数和选择状态写回 provider/audit JSON；不得提交 `production/providers/rodin/downloads/` 或与 `models/**` 重复的副本。
- status 所需 subscription token/JWT 只能临时写入被忽略的 `.agents/runtime/rodin/`，权限 0600；任务结束立即删除。
- 下载签名 URL 只存在于内存中并立即下载，不能进入 requests、responses、tasks、manifest 或日志。
- 网络超时先查现有 task，不直接创建新的付费任务。

## 非人形绑定：Tripo

用途：优先对 Rodin 或其他来源的模型执行 rig-check、非人形绑定和骨骼动画重定向。它是首选运动路线，不是唯一可接受路线。

- Quick Start：https://developers.tripo3d.ai/en/docs/quick-start
- Auto Rig：https://developers.tripo3d.ai/en/docs/animations-rig
- Animation Retarget：https://developers.tripo3d.ai/en/docs/animations-retarget
- 密钥：`TRIPO_API_KEY`。

截至本参考核对日期，Tripo Rig `v2.5-20260210` 官方列出 `quadruped`、`hexapod`、`octopod`、`serpentine`、`aquatic`、`avian` 等非人形类型。执行规则：

1. 先调用 `rig-check`，不凭外观猜 `rig_type`。
2. 使用当前官方指定的非人形 rig 模型版本与返回的 `rig_type`。
3. 绑定输出必须下载为 GLB，检查 skin、joint、weights，以及 anatomy profile 中所有主要活动区域的骨骼覆盖。
4. 官方非人形预设动作数量可能远少于双足预设。当前文档只明确列出四足 walk 及若干其他体型的基础移动，不得据此宣称能直接获得 6–10 个丰富动作。
5. 预设不足时，后续动作必须由额外明确支持的来源或代码生成的 joint tracks 补齐并烘焙进 GLB；依然需要逐动作验收。
6. 若 anatomy profile 中需要独立活动的区域没有得到骨骼覆盖，骨骼路线失败；先针对拓扑、rig 类型和 provider 迭代。确认骨骼不可行后转入高质量 morph、articulated node 或 mesh deformation 路线，不以整体摇晃代替，也不因一次绑定失败直接放弃全部运动系统。

平台任务的请求、响应、临时 URL 与下载文件遵循与 Rodin 相同的脱敏和单份留存规则。下载到 `.agents/runtime/<slug>/downloads/tripo/<task-id>/`，只把被选中的 rig/animation GLB 提升到一个版本化 `models/**` 或 `animations/**` 规范路径。

项目提供 `scripts/tripo_client.py`，支持：

```bash
python3 .agents/skills/shanhai3d/scripts/tripo_client.py --project-root . upload --collection collections/<slug> --file collections/<slug>/models/rig-source.glb
python3 .agents/skills/shanhai3d/scripts/tripo_client.py --project-root . rig-check --collection collections/<slug>
python3 .agents/skills/shanhai3d/scripts/tripo_client.py --project-root . poll --collection collections/<slug>
python3 .agents/skills/shanhai3d/scripts/tripo_client.py --project-root . rig --collection collections/<slug> --rig-type quadruped
python3 .agents/skills/shanhai3d/scripts/tripo_client.py --project-root . retarget --collection collections/<slug> --animations preset:quadruped:walk
```

先读取 rig-check 结果再选择 `--rig-type`，不要机械复制示例。客户端只保存 file token、task ID、状态、credits 数值和本地路径；下载 URL 不落盘。

## Meshy 的适用边界

- Rigging API：https://docs.meshy.ai/en/api/rigging
- Animation API：https://docs.meshy.ai/en/api/animation

截至本参考核对日期，Meshy 官方 API 文档明确说明程序化 rigging 主要适用于标准 humanoid/biped，并列出 non-humanoid 为不适合类型。网页端展示的四足能力不能自动等同于 API 能力。

- 非人形任务默认不能把 Meshy Rigging API 当作 Tripo 的等价后备。
- 只有重新核对当前 API 文档并确认目标 `body_type` 已受支持时才允许切换。
- 人形任务也必须先满足模型面数、清晰肢体和纹理等当前限制。

## 状态机

```text
initialized
→ researched
→ concept_ready
→ reference_qc_passed
→ model_submitted
→ model_qc_passed
→ detail_qc_passed
→ rig_checked
→ motion_system_selected
→ motion_qc_passed
→ animation_qc_passed
→ web_optimized
→ viewer_ready
→ verified
```

阻断状态包括：

- `blocked_credentials`
- `blocked_reference_quality`
- `blocked_model_quality`
- `blocked_detail_quality`
- `blocked_provider`
- `blocked_rig_quality`
- `blocked_animation_quality`

阻断状态不能发布首页，也不能自动绕过。

## 自动付费规则

1. 完整默认路线同时检查 `RODIN_API_KEY` 和 `TRIPO_API_KEY`；只有对应硬门通过后才调用下一 provider。
2. 名称触发后可自动推进，但每次付费提交都必须有前一质量门的落盘证据。
3. 不设置基于付费次数或 credits 的固定重试上限。每次失败必须先定位到参考图、结构、拓扑、绑定、动作或 provider 能力，并改变输入、Prompt、参数、拓扑或 provider；禁止相同条件下盲目重复提交。
4. 质量优先，不因余额充足而跳过质量门，也不因节省 credits 主动降低纹理、拓扑、动作丰富度或验收标准。
5. 无法从当前官方页面确认单价时不猜价格；最终报告只把实际调用、平台返回的 credits 和余额变化（若接口提供）作为审计信息，不作为发布判据。
6. 不保存密钥、Authorization、Cookie、账户/账单信息、轮询 token 或签名 URL。

## 错误恢复

- `401/403`：停止重试，标记凭据或权限阻塞。
- `429`：读取重试提示并有限退避。
- `5xx/网络中断`：先查询已有 task ID。
- 参考图错误：重新生成最早失败视图并重新执行完整 reference QC。
- 模型结构错误：判断是否由输入矛盾导致；不得进入 BANG 删件修复路线。
- 绑定/动作错误：保留任务元数据和必要的唯一 QC 证据，不保留重复下载；先回到模型拓扑、rig 参数或动作来源。骨骼路线确认不可行时改用可审计的 morph、articulated node 或 mesh deformation。只有所有合理运动路线都无法达到动作语义和形变质量时才阻塞。
- 临时 URL 过期：使用 task ID 重新查询，无法恢复时才重新生成。
