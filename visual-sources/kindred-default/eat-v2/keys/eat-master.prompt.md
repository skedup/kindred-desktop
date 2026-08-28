# `eat` 获准母版生成记录

状态：已批准
日期：2026-08-27
批准：用户于 2026-08-27 明确认可人物与构图

## 输出

- 获准 RGBA 母版：`eat-master.png`
- 尺寸：1024×1536
- Alpha：有
- SHA-256：`8ec3530d93e0afbc47b843a07de4091236801a17d01b6704691696bc5cee9edf`
- 512×768 预览：`../previews/eat-master-512x768.png`
- 预览 SHA-256：`5614ecb1a75d77e6fdfbe190119961b9b2579c98619193934f633eb98f2dbaec`

## 输入职责

1. `visual-packs/kindred-default/assets/body/neutral.png`
   - 人物身份、脸、发型、配色、服装和装饰语言的唯一权威。
2. `visual-sources/kindred-default/eat-v2/concepts/eat-breakfast-concept-01.png`
   - 只约束早餐姿态、人物与桌椅/碗勺的空间关系、构图和情绪。

正式母版生成未直接使用用户提供的第三方早餐场景参考图。

## 提示词

```text
Create a new clean production composite master for a frame-animated desktop spirit. This is not a room illustration and not a direct repaint of the supplied concept.

INPUT ROLES:
- The first image is the absolute authority for the character's identity, face, hair, colors, costume design, ornament language, and rendering quality.
- The second image is only the approved reference for the breakfast pose, framing, chair-table relationship, bowl-spoon interaction, gentle concentration, and warm elegant mood.
Do not copy any room decoration or extra food from the second image.

CHARACTER IDENTITY — preserve exactly:
An elegant adult East Asian anime / premium VTuber-style woman; slender graceful proportions; refined mature but youthful face; pale luminous skin; amber-gold eyes; long deep indigo-purple hair arranged in a low side bun with flowing lengths and distinctive teal inner highlights; violet crystalline hair ornament. Preserve her deep teal and midnight-navy high-collar fitted dress, fine gold botanical embroidery, violet gemstone accents, translucent lavender organza sleeves, and luxurious restrained materials. Do not simplify or redesign her clothing. No resemblance to a copyrighted named character.

APPROVED BREAKFAST ACTION:
She sits centered behind a polished dark-wood breakfast table on a curved navy upholstered chair. A shallow ivory ceramic bowl rests on the tabletop. Preserve the approved concept's hand relationship: the same hand shown holding the spoon holds exactly one slim spoon just above or barely inside the bowl, while the opposite hand gently steadies the bowl. Her head tilts slightly downward toward the action; her eyes clearly focus on the spoon and the place where it meets the bowl. Her expression is quietly attentive, elegant, awake, and natural—not blank, sleepy, childish, or broadly smiling. Include one small restrained plate with two or three simple bread pieces, secondary to the bowl.

COMPOSITION:
Portrait 2:3 canvas. Medium seated composition showing the complete head, all hair, both shoulders, both forearms and hands, torso to waist or upper thighs, chair back, full bowl, full spoon, bread plate, and a stable strip of tabletop. Table occupies the lower 30–35 percent. Near-orthographic perspective with a restrained 70–85 mm portrait-lens feel; camera 10–15 degrees front-left and only 5–8 degrees downward; torso turned 10–20 degrees toward image right. Leave comfortable motion clearance around hair, sleeves, hands, spoon, bowl, chair, and table. Avoid an oversized head or sudden zoom; desktop-spirit-readable silhouette.

RUNTIME-ASSET ISOLATION:
Place only these elements on a perfectly uniform, flat, solid chroma-key green background of exact pure #00FF00:
1) the woman,
2) the curved chair back and only the chair portions naturally visible,
3) the dark-wood tabletop,
4) the ivory bowl,
5) exactly one spoon,
6) the small bread plate.
The entire background must be uninterrupted #00FF00 pixels, with no transparency checkerboard, no room, window, wall, picture frame, flowers, fruit, teapot, carafe, extra cups, extra plates, floor, cast shadow, halo, vignette, gradient, texture, bokeh, smoke, particles, or green spill. Do not use #00FF00 anywhere inside the subject or props. Give subject edges clean antialiasing suitable for chroma-key extraction.

QUALITY:
Premium polished VTuber character art with clean stable linework, coherent anatomy, elegant fabric rendering, crisp gold embroidery, believable translucent sleeves, subtle satin and organza highlights, stable rigid bowl/chair/table geometry, and readable hands. Preserve the character as one continuous body surface; no segmented limbs, seams, floating hands, duplicated fingers, deformed shoulders, warped chest, or detached sleeves.

STRICT NEGATIVES:
No full-body standing pose; no eating while standing; no room interior; no additional people; no extra arms, hands, fingers, spoons, bowls, or food props; no cropped head, hair, hands, spoon, bowl, chair, or tabletop; no text, logo, watermark, border, contact sheet, sprite sheet, multiple panels, multiple poses, photorealism, pixel art, chibi proportions, sexualized pose, exaggerated cleavage, or low-resolution details.
```

## 初步检查

通过：

- 人物身份、发型、主配色和服装语言与 neutral 原设一致；
- 目光明确落向碗勺，表情自然；
- 两只手完整，持勺与扶碗关系可信；
- 桌、椅、碗与小面包盘几何清楚，足以作为后续固定道具；
- 构图为早餐桌后的中近景，没有完整房间和多余餐具。

转换记录：

- 内建图像生成输出为不透明绿幕 PNG；绿幕并非逐像素恒定色，左上 180×180 区域的 `signalstats` 为 `Y 143–146 / U 59–66 / V 36–46`；
- 使用 FFmpeg `chromakey=0x00ff00:0.20:0.035,despill=green:mix=0.35,format=rgba` 转换为获准 RGBA 母版；
- 检查确认人物、半透明袖、青色发丝、桌椅和餐具边缘没有明显误切；
- 原始绿幕中间件在获准 RGBA、预览和 SHA-256 写入后移除，不作为回滚资产保留。
