# Shanhaiworld

《山海经》神兽 PC 端 3D 图鉴。每只神兽拥有独立页面、模型、丰富动作、协调场景和完整生产记录，同时复用公共 Three.js 查看器与站点样式。

## 使用方式

在 Codex 中只提供名字：

```text
$shanhai3d 九尾狐
```

Skill 自行完成考据、Prompt、参考图、3D、绑定、动画、场景和网页，不要求用户准备图片或使用 Blender。

“全自动”不代表降低质量。流程有五个不可绕过的门：

1. 先为该神兽建立专属 anatomy profile，再检查适用的数量、连续结构、活动区域、表面特征和跨视图一致性；没有尾巴就不会出现尾巴检查。
2. 生成的 3D 结构本身准确，不能靠删除错误组件把错误结构修剪成“合格”。
3. 毛发、鳞片、羽毛、面部和 PBR 材质在近景中清楚可辨。
4. 首选与身体类型匹配的真实 skin、weights 和骨骼；特殊体型无法可靠绑定时，允许使用高质量 morph、分段节点或 hybrid 形变，但必须真实驱动身体局部。
5. 页面至少有 6 个与该神兽行为相符的动作；每个动作有准备、主体和恢复，整体上下浮动、旋转、缩放或只有世界位移不算身体动画。

任一门失败时，Skill 不会把弱化版发布到首页。流程以质量为先，不设基于 API credits 的固定重试上限；每次重试必须针对已诊断的根因改变输入、参数、拓扑、动作来源或 provider。

## 生产路线

```text
名称与考据
→ 视觉主稿
→ 专用建模多视图
→ 参考图质量门
→ Rodin 高质量源模型
→ 结构与细节质量门
→ 骨骼优先的运动系统选择
→ 6+ 语义动作与形变质量门
→ PC 网页优化
→ 场景与 Three.js 交互
→ 1920×1080 浏览器验收
→ 首页发布
```

视觉主稿负责审美，建模图只为 3D 重建服务。建模图使用与体型相符的冻结姿势、中性光和纯色背景。可计数结构检查边界和数量，连续身体检查轮廓、体积与连接，活动区域检查关节和活动空间；不适用项明确跳过。Prompt 写了 `exactly N` 不算自检通过，必须查看原始分辨率并留下 QC 证据。

## 项目结构

```text
shanhaiworld/
├── .agents/skills/shanhai3d/
├── .env.example
├── index.html
├── assets/
│   ├── css/site.css
│   ├── data/collections.json
│   ├── js/home.js
│   ├── js/collection-page.js
│   ├── vendor/three/
│   └── templates/collection/
├── collections/
│   └── <slug>/
│       ├── index.html
│       ├── collection.json
│       ├── preview.webp
│       ├── concepts/
│       ├── views/
│       ├── models/              # raw.glb / rigged.glb / web.glb
│       ├── animations/
│       ├── scene/
│       ├── production/          # Prompt、原图、失败版本、脱敏任务记录
│       └── reports/             # reference/model/detail/rig/animation QC
├── README.md
└── AGENTS.md
```

首页读取 `assets/data/collections.json`，只显示 `ready` 条目。每只神兽独立页面复用公共 Three.js 运行逻辑；动作菜单只读取最终 GLB 中实际存在的 clips。

## 本地密钥

图片使用 Codex 内置 ImageGen，不需要 `OPENAI_API_KEY`。完整默认路线需要：

```dotenv
RODIN_API_KEY=你的 Hyper3D 密钥
TRIPO_API_KEY=你的 Tripo 密钥
MESHY_API_KEY=
```

- `RODIN_API_KEY`：高质量静态 3D 生成。
- `TRIPO_API_KEY`：首选的非人形 rig-check、绑定和骨骼动画来源；不支持特殊体型时自动评估高质量形变路线。
- `MESHY_API_KEY`：可选；只有当前 Meshy API 明确支持目标身体类型时使用。当前不能把网页端四足能力等同于 API 四足绑定能力。

根目录 `.env` 已被 Git 忽略。进程环境变量优先于 `.env`；工具只报告密钥是否配置，不显示密钥内容。

项目内置 `rodin_client.py` 和 `tripo_client.py`，可自动提交、轮询、下载、rig-check、绑定和动画重定向；请求/响应记录会脱敏，临时 JWT 与签名下载地址不会进入 `production/`。

检查环境：

```bash
python3 .agents/skills/shanhai3d/scripts/check_environment.py --project-root . --strict
```

## 本地预览

浏览器模块和 JSON 需要 HTTP 服务，不能直接双击 HTML：

```bash
python3 .agents/skills/shanhai3d/scripts/serve.py --project-root . --port 4173
```

访问 `http://localhost:4173/`。安全预览服务会拒绝访问 `.env`、`.agents` 和每只神兽的 `production/`。

项目只针对 PC 桌面浏览器；源模型先保证结构、表面和运动质量，最终 `web.glb` 再通过减面、Meshopt/Draco 和 KTX2 平衡画质与实时性能。不会为了省积分主动降级源模型、纹理或动作质量。
