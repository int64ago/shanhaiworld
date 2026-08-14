# Shanhai3d 质量门

在生成参考图、提交付费 3D、绑定、动画和最终发布前读取。本文件定义阻断条件；检查失败时必须回到最早的错误阶段。

## 1. 参考图门

### 两套图，两种目的

- **视觉主稿**：确定身份、比例、配色、毛发/鳞片/羽毛语言和神态，可使用克制的戏剧光照。
- **建模输入图**：只为多视图重建服务，使用正交或长焦近正交镜头、冻结姿势、中性光、纯色背景、完整身体和清楚负空间。

不要把气氛插画直接送给 3D 平台。插画里的景深、雾、强反光、遮挡、飞散毛发和夸张透视会被重建为错误几何或糊贴图。

### 先建立 anatomy profile

每张候选图都必须用原始分辨率检查；关键区域再以至少 200% 查看。检查项不是固定的“尾巴清单”，而是从考据与设计中生成该生物自己的 `anatomy_profile`：

- `counted_features`：真正需要锁定数量且边界可辨的结构，例如角、翼、足、眼或尾。没有可计数结构时写 `not_applicable`。
- `continuous_features`：更应检查连续性、体积或分支拓扑的结构，例如蛇身、鱼鳍、甲壳、躯干或云气形身体，不硬套数量规则。
- `articulated_regions`：需要独立活动或连续弯曲的身体区域及其连接位置、活动方向和遮挡关系。
- `surface_features`：毛束、鳞片、甲片、羽层、皮肤褶皱、纹路等必须在模型中真实可读的表面语言。
- `locomotion_modes`：站立、行走、爬行、飞行、游泳、盘绕、漂浮等实际运动方式。
- `not_applicable`：明确列出不适用的类别，防止无尾生物也被要求“从根到尖计数”。

据此动态检查：

- 只有 `counted_features` 才检查数量；每项必须与锁定特征一致且边界清楚。
- `continuous_features` 检查轮廓、体积、连接和分支拓扑，不以末端数代替整体结构判断。
- 需要独立活动的区域必须看清连接、分段、活动空间与相邻结构关系；多个同类结构只有在确实存在时才要求可辨负空间。
- 左右视图不是三分之四视图；相反侧不能用镜像图冒充真实信息。
- 所有提交视图必须保持同一冻结姿势、附肢展开角度、身体比例、花纹、材质和光照。
- 任一视图在适用结构上出现无依据的新增、消失、分叉、合并或比例变化时，该视图直接失败。宁可少提交一张，也不向多视图条件注入矛盾。
- 图片上的文字、编号、箭头、标尺或人工 QC 标记只能出现在审计副本，不能进入 provider 输入图。

### 适配 3D 重建的 Prompt 要点

- 写明 `single isolated creature`、完整身体、与其身体类型匹配的中性冻结姿势、正交/长焦和均匀工作室光。
- 从 `anatomy_profile` 动态写约束：可计数结构写 exact count 与边界分离；连续结构写 continuity、volume 和 branch topology；关节区域写 clear attachment、articulation range 和 unobstructed silhouette。
- 表面语言按实际类型写：毛发用 layered sculpted fur clumps；鳞甲用 separated scale/plate relief；羽毛用 layered feather groups；皮肤用 pores/folds/roughness variation。不存在的材质不写。
- 负面约束包含 cropped body、occlusion、motion blur、depth of field、fog、rim-light bloom、smooth clay、plastic fur、painted fur blur、extra/fused/missing appendages。

### 必须落盘的 `reports/reference-qc.json`

至少包含：

```json
{
  "status": "passed",
  "checked_at": "ISO-8601",
  "images": [
    {
      "path": "views/front.png",
      "role": "provider_input",
      "original_resolution_checked": true,
      "checks": {
        "anatomy_profile_defined": "passed",
        "applicable_counts": "not_applicable",
        "continuous_structure_integrity": "passed",
        "articulation_visibility": "passed",
        "cross_view_consistency": "passed",
        "material_legibility": "passed",
        "clean_background": "passed"
      },
      "evidence": "可复查的具体描述"
    }
  ],
  "provider_inputs": ["views/front.png", "views/back.png"],
  "blocking_failures": []
}
```

`prompt says exactly N`、文件存在或缩略图看起来正常都不是通过证据。

## 2. 模型门

生成后先验证高质量源模型，不先减面、不先绑骨。

- 保存无场景的 8 方位转台渲染。
- 保存身份特征、主要连接/关节区域、轮廓转折和关键材质近景；具体清单来自 `anatomy_profile`。
- 结构数量与连接关系必须准确；没有重复壳、悬浮块、破面、融合肢体或异常洞。
- 标志结构必须是真实连续几何，不能靠删除错误组件留下不自然残根或断面。
- BANG/拆件只用于检查、材质整理或在本来正确的模型上做合理分组，不能把错误生成结构修剪成“表面合格”。
- 失败时判断根因：所有 3D 尝试都重复同一错误通常说明参考图不合格，应回到参考图门。

`reports/model-qc.json` 至少记录源文件、转台/近景证据、结构检查、拓扑问题、provider 尝试次数和最终状态。

## 3. 表面与材质门

表面特征不能只靠 albedo 上的模糊明暗伪装。按 `surface_features` 检查：

- 毛发需要可读的毛束方向、轮廓破形、normal 起伏和 roughness 层次，不是光滑气球或一团糊贴图。
- 鳞片、甲片、羽层需要可辨边界、合理叠压、厚度/法线变化和材质反射差异，不是平面花纹。
- 裸露皮肤、角质、湿润组织和硬质爪角应有各自尺度的褶皱、孔隙、粗糙度与高光，不糊成同一块。
- 眼、口、角、爪等身份区域与主体材质分离；浅色区域放在中灰背景检查，避免过曝吞细节。
- 正常页面镜头能读到中尺度表面层次，近景能读到方向或叠层，但不盲目追求逐根毛发或无限几何细分。
- 优化前后使用同镜头、同灯光对比。压缩或减面导致脸、标志轮廓、表面层次或花纹明显退化时失败。

`reports/detail-qc.json` 记录源/网页纹理分辨率、PBR 通道、关键近景和对比结论。

## 4. 运动系统门

静态模型可看不等于可动画。首选 `skeletal`，因为它通常最适合丰富动作和混合；若 provider 无法为特殊体型生成合格蒙皮，可使用 `morph`、`articulated` 或 `hybrid`，但质量门不降低。

- `skeletal`：至少 1 个 skin，存在 JOINTS/WEIGHTS，关节层级可解析；骨骼覆盖 `articulated_regions`，逐个测试关键关节后没有明显塌陷、拉丝或错误牵连。只有骨节点而无有效权重视为失败。
- `morph`：模型存在 morph targets，动画 clip 实际驱动 weights；目标覆盖主要表情、形变和运动相位，不是只做全身缩放。
- `articulated`：模型被合理分段且节点连接没有裂缝；动画同时驱动多个有语义的身体节点，轴心、层级和活动范围符合解剖。
- `hybrid`：组合上述路线，并分别满足所使用路线的证据要求。
- 任意模式都必须覆盖 anatomy profile 中的主要活动区域；整体 actor/model root 的平移、旋转、缩放或上下浮动不构成身体动作。

把 `motion_mode`、实际驱动目标、覆盖区域、变形异常和测试证据写入 `reports/rig-qc.json`。若骨骼尝试失败，还要记录失败原因和选择替代模式的依据。

## 5. 动画门

发布至少需要 6 个通过检查、与生物结构和行为相符的动画：

- 1 个循环待机。
- 1 个与体型匹配的循环移动；根据 `locomotion_modes` 选择行走、奔跑、飞行、游泳、爬行、盘绕或漂浮，不强套四足步态。
- 至少 4 个明显不同的观察、转向、攻击、鸣叫、受击、跳跃、起飞、降落、飞行、游泳或标志展示动作。

每个动作必须：

- 实际驱动 joints、morph weights、分段身体节点或可审计的网格形变，让主要身体区域发生局部、连续且有语义的变化。
- 具有准备、主体和恢复相位；循环移动要能看出步态、振翅、躯干波动、鳍肢划水或该生物适用的推进机制。
- 至少影响两个有语义的身体区域，或一个覆盖身体主要长度的连续形变场；纯 root motion 不算。
- 循环动作首尾连续；一次性动作能回到待机。
- 无严重滑动、穿模、局部翻转、形变爆炸、活动结构脱离、接缝裂开或根节点瞬移。
- 多个重复结构在确实存在时要有合理错相和层次，不能机械地完全同步。

以下不计入动作数量：

- 移动或旋转整个 actor/model root。
- 整体上下浮动、缩放呼吸、镜头运动、粒子或材质闪烁。
- 只有名字不同、姿态几乎相同的重复 clips。

平台预设不足时，允许用代码生成 joint、morph 或 articulated node tracks 并烘焙进 GLB；也允许把确定性网格形变逻辑作为随 collection 保存的动画资源，但必须可复现、可审计并逐动作验收。`reports/animation-qc.json` 对每个动作至少记录：

- `name`、`expected_behavior`、`observed_behavior` 和 `motion_mode`。
- `driven_regions`、`preparation_main_recovery`、`loop_or_return` 和 `browser_evidence`。
- `semantic_match`、`deformation_quality`、`contact_or_propulsion`、`transition_quality` 和最终 `status`。

名字叫 `Attack` 不代表动作像攻击；只有观察结果与预期行为相符才通过。

## 6. 网页与发布门

- `inspect_glb.py --motion-mode <skeletal|morph|articulated|hybrid> --min-animations 6` 通过。
- Three.js 动作菜单只显示实际可播放动作；页面按声明的 `motion_mode` 验证 skin、morph targets 或动画节点，而不是无条件要求 skin。
- 自动游走播放对应 locomotion 身体动作，世界位移仅承担路径推进。
- 在 1920×1080 检查正常距离和近景细节、全部动作、鼠标旋转/缩放/点击、场景融合、控制台和性能。
- `manifest.json` 中所有硬门都有可复查 evidence；任何一门失败时 collection 与 catalog 都不能是 `ready`。
