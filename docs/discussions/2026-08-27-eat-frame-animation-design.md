# `eat` 坐姿帧动画设计

状态：实施中（母版、动画与本机视觉验收已通过，等待定向 review）
日期：2026-08-27

## 1. 结论

`eat` 的下一版不再修补现有站姿 FRAME1，而是按 `draw` 已验证的方式重做：

- 角色改为坐在早餐桌后的中近景进食；
- 椅子、桌面、碗和少量早餐道具保持绝对静止；
- 桌沿与碗前沿作为独立前景遮挡层；
- 人物使用一张完整、连续的角色表面做局部形变，不再切分大小臂或躯干；
- 勺子作为刚性小道具独立运动，但始终锚定在手中；
- 动画采用 84 帧、12 FPS、7 秒闭环；
- 先验收母版和预览，再以哈希一致的方式发布到运行时资源。

这会替换当前“站立持碗、少量关键图硬切换”的表现。它不改变 action、manifest 格式或 renderer 架构。

## 2. 为什么沿用 `draw`

当前 `eat` 的机械感主要不是帧数不足，而是制作模型不适合：少数完整关键图通过停顿和切换组成动作，人物姿态、碗和勺子之间没有连续的运动关系。

`draw` 已经验证了更可靠的生产约束：

1. 固定场景道具与人物运动分层；
2. 人物保持为连续表面，避免手臂切片产生接缝；
3. 笔一类细长道具使用刚性图层，避免随人物网格弯曲；
4. 只从一张批准的角色母版做确定性形变，不让模型逐帧重画；
5. 通过静态区域、闭环、身份一致性和发布哈希验证后再进入 visual pack。

参考现有实现：[FRAME2E source notes](../../visual-sources/kindred-default/frame2e/README.md) 与 [visual pipeline responsibilities](../../tools/visual_pipeline/README.md)。

## 3. 用户看到的动作

### 3.1 场景

- 角色居中坐在深蓝色雕花椅上，保持当前原创角色的人脸、深紫发色、青绿色内层挑染、琥珀色眼睛和深青蓝礼服。
- 采用早餐桌前的中近景构图：人物显示到腰部或上腿，桌面占画布下方约 30%–35%，腿部由桌沿自然遮挡。
- 角色正前方只有一个浅口陶瓷碗；画面一侧可放一只小面包盘，但不保留概念图中的水果盘、花瓶和完整室内陈设。
- 靠近碗、位于画面右侧的手持细柄勺，另一只手轻扶碗侧；两只手必须完整、清楚，并留出后续运动空间。
- 最终运行时是透明背景上的人物、椅子与早餐桌组合，不保留矩形房间背景，避免在桌面上呈现为一张海报。
- 早餐桌在 512px runtime 画布两侧各保留 17px 透明边距；映射到 304px 舞台后，
  桌面有效宽度约为 284px，与底部状态标签对齐，而人物与椅子保持原比例。
- 人物头部的屏幕尺度不得超过 `draw` 的约 1.15 倍，避免 action 切换时出现突兀的镜头放大。

V1 选择“碗 + 勺 + 小面包盘”，以保留早餐氛围，同时控制手部接触、遮挡和静态道具数量。

### 3.2 相机与透视

采用近似正交的轻微俯视、近正面的三分之四视角。目标是让脸、双手、勺和碗成为视觉中心，并由桌面形成稳定的前景基座。

- 相机位于人物正前方偏左约 10°–15°，光轴对准坐姿胸腹之间；
- 相机仅轻微俯视约 5°–8°，使碗、勺和双手可见但不形成俯拍；
- 人物躯干朝画面右侧旋转约 10°–20°，整体仍接近正面；
- 脸轻微朝画面右下方转动，眼睛明确看向勺尖或碗；
- 画面呈现类似 70–85mm 镜头的压缩感，竖线近似平行，避免广角近大远小；
- 椅背从人物肩膀后方少量露出，桌面横向穿过画面下方；
- 碗顶呈浅椭圆，只显示少量内沿；桌沿不能高到遮挡双手或碗；
- 人物下半身由桌沿自然遮挡，不为动画额外生成不可见的完整腿部。

构图关系为：

```text
              画面后方

                 椅背
                  │
相机  ↑         人物
              手—勺—碗
            ─── 桌面 ───

              画面前方
```

禁止证件照式完全正面、明显侧面和明显俯拍；桌面不能占据一半画面，也不能用前景餐具遮住手部。

### 3.3 七秒闭环

| 时间 | 动作 |
| --- | --- |
| 0.0–0.8 s | 安静坐姿，小幅呼吸，视线落在碗和勺附近 |
| 0.8–2.1 s | 上身轻微前倾，持勺手将勺伸向碗内 |
| 2.1–3.4 s | 勺子缓慢抬起，眼睛和头部跟随勺尖 |
| 3.4–4.2 s | 完成一口进食，嘴部只做克制的小动作 |
| 4.2–5.8 s | 手臂与勺子回落，上身回正 |
| 5.8–7.0 s | 回到初始坐姿并完成闭环 |

动作要比现有 `eat` 明显，但不能像夸张表演：主要位移来自持勺手、半透明袖、头部和上身重心；裸肩与胸部作为刚性核心，只随上身整体移动，不被持勺手局部拉伸。扶碗手只做维持接触的轻微联动。

## 4. 图层与运动模型

### 4.1 后景静态层

后景静态层包含：

- 椅背与不被人物遮住的椅子结构；
- 桌面表面；
- 碗的后半部与内部；
- 小面包盘。

这些内容在 84 帧中像素位置、尺寸、透视和轮廓必须保持一致。人物运动不能推动或拉伸它们。

完整房间、窗户、墙画和花瓶只属于概念图，不进入运行时后景层。运行时画布其余区域保持透明。

### 4.2 连续人物表面

人物从头发到被桌沿遮住的下躯干是一张完整 RGBA 表面。局部网格可以对肩、肘、腕、头、胸廓和腰施加连续形变，但不得把手臂、头部或躯干拆成独立贴片。

必须满足：

- 裸肩、锁骨和胸部只随上身刚性移动，抬手局部形变从金属臂环以下开始；
- 胸部和里侧肩膀不随持勺手拉伸；
- 腰与大小臂没有接缝；
- 头部移动后原位置不残留头发或面部像素；
- 服装刺绣、半透明袖和靴子纹样不发生局部融化。

### 4.3 刚性勺子

勺子从获准母版中提取为独立 RGBA 层，围绕手部锚点做平移与旋转：

- 长度、粗细和勺头形状逐帧不变；
- 手掌与勺柄接触点不漂移；
- 勺尖路径从碗内到嘴边再返回；
- 不穿过脸、手、碗沿或桌面；
- 闭环首尾的位置和角度完全一致。

V1 不表现勺中的具体食物，以免小尺寸下产生闪烁或错误语义。

### 4.4 前景遮挡层与验证 mask

前景遮挡层是实际参与合成的 RGBA 内容，包含：

- 桌面前沿；
- 碗的前沿与前半部；
- 必要时位于最前方的小面包盘边缘。

它在人物和勺子之后合成，使下躯干自然位于桌后，也使勺子伸入碗中时能被碗前沿正确遮住。

另外生成静态区域验证 mask。该 mask 不参与显示，只用于证明后景和前景道具在所有帧中保持字节稳定。两者不能混为同一个文件。

合成顺序固定为：

```text
透明画布
  → 后景静态层（椅背、桌面、碗后部、面包盘）
  → 连续人物层
  → 刚性勺子层
  → 前景遮挡层（桌沿、碗前部）
```

运行时源资产仍严格保持上述四层。为了正确表达“手指压在勺柄上、扶碗手位于
碗前、碗前沿压在下躯干前方”的深度关系，合成器会在固定前景之后，从同一张
连续人物表面确定性重放扶碗手和握柄手指区域。重放区域不是第五张资产，也不是
独立肢体贴片；它与人物主体使用完全相同的连续网格形变，肩、胸、手臂和手始终
来自同一张连续人物表面。人物纹理本身不烙入随身体移动的碗形孔洞。

## 5. 角色母版生成合同

只生成一张可批准的完整母版。后续 84 帧均由确定性工具产生，不使用独立逐帧生成、视频补帧或 optical flow。

### 5.1 母版提示词

以下提示词供后续 source master 生成。实际执行时使用项目自有 neutral 图作为身份约束，并使用已生成的 `eat-breakfast-concept-01` 作为场景关系参考；用户提供的第三方场景图不直接进入正式母版生成。

```text
Create a clean production composite master for a desktop spirit frame animation.

Preserve the exact original Kindred woman from the identity reference: her adult East Asian anime-inspired face, luminous fair skin, calm amber-gold almond eyes, deep indigo-purple hair in a loose side bun with teal inner highlights, violet crystal hair ornament, mature elegant proportions, and recognizable expression. Preserve the established deep teal/navy high-collar dress, fine gold botanical embroidery, asymmetric violet panels, translucent iridescent lavender organza sleeves, gold arm bands, and violet crystal ornaments. Preserve premium material separation: dense matte silk, fine metallic embroidery, translucent organza, crisp gemstones, controlled highlights, coherent folds, precise clean edges, and subtle luminous skin. No mottled AI texture.

Use the approved breakfast concept only for its scene relationship: the woman sits centered behind a polished dark-wood breakfast table, with the curved dark navy chair back subtly visible behind her. Place one shallow ivory ceramic bowl directly in front of her and one small plate of warm bread to the side. Her image-right hand holds exactly one slim spoon just above or barely inside the bowl, ready to scoop. Her opposite hand gently steadies the side of the bowl. Both hands are completely visible and anatomically correct. Her head inclines slightly down and right, and her eyes clearly focus on the spoon tip or bowl with a calm, quietly content, living expression.

Use a portrait 2:3 canvas and a medium seated composition from the head to the waist or upper thighs. The tabletop occupies the lower 30–35 percent of the canvas and naturally hides the legs. Use a near-orthographic restrained 70–85mm perspective, camera about 10–15 degrees toward her front-left, with only a 5–8 degree downward angle. Her torso turns about 10–20 degrees toward image right. Keep vertical lines nearly parallel. Show the bowl rim as a shallow ellipse with only a little interior visible. Keep generous motion clearance around both forearms and the spoon. Keep the apparent head scale no more than about 1.15 times the existing draw action.

Isolate only the woman, chair, breakfast tabletop, bowl, spoon, and small bread plate on one perfectly uniform pure chroma green background (#00FF00). The green must be a single flat color with no room, window, wall, picture frame, flower, fruit plate, vase, floor, cast shadow, gradient, texture, glow, or lighting variation. Do not use #00FF00 anywhere in the subject.

This is a reusable animation master, not a poster. Do not crop the head, hair, hands, spoon, bowl, chair back, or visible table edges. Avoid a certificate-photo frontal pose, strict side profile, top-down view, dramatic low angle, or wide-angle distortion. Do not redesign the character. Do not make her chibi, childish, photorealistic, western-comic styled, pin-up posed, or exaggeratedly sexy. Do not add extra people, hands, fingers, utensils, bowls, cups, food particles, steam, napkins, text, logos, scenery, or decorative effects. Do not deform the chair, table, bowl, hands, face, outfit patterns, or sleeves.
```

### 5.2 母版批准条件

生成结果只有同时满足以下条件才进入分层：

- 一眼可认作当前 Kindred 原创角色，而不是新的相似人物；
- 坐姿自然、端庄，头和眼睛明确看向勺或碗；
- 中近景从头部延伸至腰部或上腿，桌面占下方约 30%–35%，头部尺度不超过 `draw` 的约 1.15 倍；
- 相机是轻微俯视、接近正面的三分之四视角，竖线近似平行，碗呈浅椭圆，手臂没有广角畸变；
- 两只手完整，勺子只有一把，接触关系可信；
- 椅背、桌面、碗和小面包盘几何清楚，没有透视错误；
- 背景是可稳定色键的纯绿，不包含完整房间、水果盘、花瓶或其他遮挡物；
- 材质彼此可区分，没有斑驳纹理、塑料感或过曝皮肤；
- 完整构图在 512×768 缩略预览中仍能读出“正在进食”。

未通过母版批准前，不编写动作工具，也不生成批量帧。

## 6. 源码与资源布局

不再继续扩大 `FRAME1/FRAME2` 这种跨 action 编号。新资源使用 action 语义命名：

```text
visual-sources/kindred-default/eat-v2/
  concepts/
  keys/
  layers/rear-static/
  layers/character/
  layers/spoon/
  layers/foreground-occluder/
  layers/validation-masks/
  frames/
  previews/
  RENDERED.txt

visual-packs/kindred-default/assets/body/eat-v2/
  eat-000.png ... eat-083.png

tools/visual_pipeline/
  eat_contract.py
  eat_generate.py
  eat_promote.py
  eat_validate.py
```

`motions/eat.json` 仍是运行时入口，只把帧目录和时间表切换到 `eat-v2`。旧 FRAME1 `eat` 在非正式阶段直接替换，不保留运行时双读、兼容分支或回滚资产。

## 7. 验收合同

### 7.1 文件与发布

- 84 张 512×768 RGBA PNG；
- 12 FPS、总时长 7 秒；
- 首帧与末帧闭环连续，最终回到同一基准；
- `RENDERED.txt` 记录获准 source、预览和运行时文件的 SHA-256；
- promotion 是事务性的；source 与 runtime 帧逐个哈希一致；
- reduced-motion 继续使用获准的静态首帧。

### 7.2 静态场景

- 后景静态层与前景遮挡层各自的可见语义 mask 内逐帧字节不变；
- 不出现全图漂移、缩放、相机位移或透明边角闪烁；
- 桌面两侧 gutter 在所有帧中保持透明，避免前景宽于底部状态标签；
- 道具不因角色运动被拉伸或遮罩误切。

### 7.3 人物运动

- 持勺手、腕和臂环以下袖子有可测运动；裸肩与胸部保持刚性，只参与上身整体位移；
- 头和视线跟随勺尖，不能平视前方或眼神呆滞；
- 上身有克制的前倾与回正，扶碗手有轻微自然联动；
- 支撑侧肩、胸部和腰部稳定，不随活动手臂发生异常形变；
- 身体任何位置无裂缝、重影、残影或缺失手帧；
- 人脸、发型、服装轮廓和材质在全循环中保持身份一致。

### 7.4 勺子路径

- 勺子全程为刚性物体；
- 路径至少覆盖“碗内—抬起—嘴边—返回”；
- 接近嘴部时速度减小，不做机械匀速往返；
- 不与脸、手、碗和桌面发生可见穿插。

## 8. 明确不做

本次不包括：

- Live2D 或骨骼动画；
- 多种食物、餐具或随机动作；
- 咀嚼音效和互动；
- renderer、action 数据模型或远端 API 修改；
- 同时重做 `settle`、`sleep` 或 `walk`；
- AI 逐帧生成、视频转帧、光流补帧；
- 为旧 FRAME1 保留正式环境兼容或回滚路径。

## 9. 设计闸门

进入实现前只需确认本稿。实现过程中保留两个视觉闸门：

1. **母版闸门**：确认角色、坐姿、道具、材质和构图；
2. **动画闸门**：确认 84 帧预览的节奏、视线和身体联动。

两个视觉闸门均已通过；获准的 84 帧已完成哈希锁定、事务性 promotion，并更新
visual pack manifest。macOS 固定 320×540 shell 的连续播放、状态切换、透明窗口、
常驻最前端和 reduced-motion 验收也已通过；下一步是定向代码与资源 review。
