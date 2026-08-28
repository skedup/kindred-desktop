# `eat-v2` 隐藏表面与刚性勺子修复板

日期：2026-08-27
模式：OpenAI 内建图像编辑 + 确定性 FFmpeg 转换

这些文件不是可独立显示的运行时帧。`keys/eat-master.png` 仍是人物身份、构图和正常可见人物像素的权威；修复板只提供动作后可能露出的隐藏表面，刚性勺子板只提供连续且可旋转的完整勺子。

## `fixed-props-clean.png`

输入：获准 `keys/eat-master.png`。
SHA-256：`6feca8aaedbf0e2f5af81732eb5b7b5c4f87d3b6f349ce3b1e4f602812f32568`

```text
Use case: precise-object-edit
Asset type: hidden-surface clean plate for the fixed breakfast props of an original VTuber desktop-spirit frame animation.

Image 1 is the only edit target and the absolute authority for canvas size, camera, pixel alignment, chair geometry, table geometry, bowl geometry, bread plate geometry, materials, colors, lighting, perspective, scale, and placement.

Create an exactly aligned clean fixed-props plate. Remove only the entire woman and the spoon: remove her head, hair, face, body, clothing, sleeves, jewelry, both arms, both hands, and every visible spoon pixel. Reconstruct only the static surfaces hidden behind those removed elements: complete the curved dark-navy upholstered chair back and its polished carved wood frame; complete the polished dark-wood tabletop; complete the shallow ivory ceramic bowl, including the small areas hidden by her supporting hand and spoon; preserve the existing small bread plate and bread exactly where they are. The result should contain only the chair, table, bowl, and small bread plate.

Preserve exact 1024×1536 portrait framing and exact object coordinates. Do not move, resize, rotate, restyle, beautify, or regenerate any already-visible part of the chair, table, bowl, plate, or bread. Keep the same near-orthographic perspective, lighting direction, colors, gold trim, wood grain, upholstery, ceramic design, and shallow bowl ellipse. Reconstruct hidden surfaces naturally and continuously, but do not invent additional props or scenery. This is a localized removal and hidden-surface repair plate, not a new composition.

Place the isolated fixed props on a perfectly flat, solid, uniform pure #00FF00 chroma-key background. No transparency checkerboard. The green field must have no gradient, texture, shadow, glow, halo, reflection, room, wall, window, floor, vignette, bokeh, or lighting variation. Do not use #00FF00 inside the props.

No woman, body fragment, hair, skin, hand, finger, sleeve, jewelry, spoon, ghost silhouette, human-shaped shadow, extra bowl, extra plate, extra bread, teapot, cup, fruit, flowers, napkin, text, logo, watermark, cropped props, changed table edge, warped chair, altered bowl, changed bread arrangement, wide-angle distortion, mottled texture, or green spill.
```

## `character-clean.png`

输入：获准 `keys/eat-master.png`。
SHA-256：`3a528fcf32e69f0707ce8e81e3c20e859c423fd35b6eab99d49d232703c3d22a`

```text
Use case: precise-object-edit
Asset type: hidden-surface clean plate for the continuous character surface of an original VTuber desktop-spirit frame animation.

Image 1 is the only edit target and the absolute authority for the woman's identity, face, hair, expression, pose, anatomy, camera, proportions, outfit, materials, lighting, framing, scale, and pixel placement.

Create an exactly aligned clean character plate. Remove only all fixed breakfast props and the spoon: remove the chair, entire table, bowl and its food, bread plate and bread, and every spoon pixel. Keep the complete woman in exactly the same seated pose and alignment. Reconstruct only the character surfaces hidden by those removed objects: complete the lower torso, waist, violet sash, dark teal/navy dress and gold embroidery down to the upper thighs; complete the supporting hand and every finger where the bowl currently overlaps it; complete the spoon-holding hand and fingers where the spoon handle currently overlaps them; complete any small sleeve, wrist, dress, or hair regions hidden by the removed props. The result should contain only one continuous complete woman from the head through the upper thighs, including both complete arms and both complete hands, with no chair, table, bowl, bread, plate, or spoon.

Preserve exact 1024×1536 portrait framing, camera, character scale, head position, torso position, shoulder positions, arm pose, hand pose, gaze, facial expression, hair silhouette, costume design, embroidery, crystals, translucent organza sleeves, skin tone, and lighting. Do not move, resize, rotate, restyle, beautify, or regenerate already-visible character regions. Reconstruct only hidden character surfaces. Her spoon-holding hand remains gently curved in the existing grip pose but holds nothing; the opposite hand remains in the existing bowl-support pose but holds nothing. Maintain anatomically correct hands and continuous shoulders, chest, waist, sleeves, and arms. This is localized removal and hidden-surface repair, not a redesign or new pose.

Place the isolated woman on a perfectly flat, solid, uniform pure #00FF00 chroma-key background. No transparency checkerboard. The green field must have no gradient, texture, shadow, glow, halo, reflection, room, wall, window, floor, vignette, bokeh, or lighting variation. Do not use #00FF00 inside the woman.

No chair, table, bowl, food, bread, plate, spoon, cup, scenery, prop fragment, ghost edge, object-shaped shadow, new pose, standing pose, crossed arms, missing hand, missing finger, extra limb, extra finger, duplicated hand, changed face, changed gaze, changed hairstyle, changed hair color, changed costume, added ornament, exposed underwear, exaggerated cleavage, body redesign, deformed shoulder, warped chest, broken sleeve, mottled texture, plastic shine, text, logo, watermark, cropping, or green spill.
```

## `spoon-complete.png`

输入：获准 `keys/eat-master.png`。
SHA-256：`5c361fe1d4cb0853fe6a1b8f9773d26732a4eed17fd048c5466b3f5e3c51352d`

内建编辑首先移除了人物和其他道具，只保留完整勺子；模型保持了方向，但输出尺寸和位置不符合像素对齐约束。该结果没有直接作为遮罩，而是经过以下确定性归一化后作为刚性勺子底板：

```text
chroma key: chromakey=0x00ff00:0.30:0.025,despill=green:mix=0.35
source visible bounds: x=167..800, y=525..962
crop: 634×438 at (167,525)
scale: 295×193, Lanczos
pad/alignment: 1024×1536 at (177,865)
transparent RGB cleanup: alpha <= 8 becomes RGBA 0,0,0,0
```

原始提示词：

```text
Use case: precise-object-edit
Asset type: semantic extraction plate for one rigid spoon in an original VTuber desktop-spirit frame animation.

Image 1 is the only edit target and the absolute authority for canvas size, camera, pixel alignment, spoon position, spoon angle, spoon length, spoon width, spoon-bowl shape, metal color, highlights, and every visible spoon pixel.

Keep only the single spoon currently held in the woman's hand, in exactly the same position, rotation, scale, shape, and pixel alignment. Remove the woman, both hands, all clothing and hair, chair, table, ceramic bowl, bread plate, bread, food outside the spoon, and every other object. Reconstruct only the tiny spoon portions hidden between her gripping fingers so the result is one complete continuous rigid spoon. Preserve the small amount of food already resting in the spoon bowl as part of the spoon extraction plate. Do not move or redesign the spoon.

Place the isolated spoon on a perfectly flat, solid, uniform pure #00FF00 chroma-key background. No transparency checkerboard, gradient, texture, shadow, glow, halo, room, floor, vignette, or green spill. Do not use #00FF00 in the spoon.

Exact 1024×1536 portrait framing and exact original spoon coordinates. One spoon only. The handle must remain straight and slender; the spoon bowl must remain rigid and undistorted. This plate will be used only to derive a semantic mask, so do not beautify, enlarge, recenter, rotate, or add presentation effects.

No person, skin, fingers, hand fragments, sleeve fragments, bowl, chair, table, bread, plate, extra utensil, fork, knife, extra spoon, text, logo, watermark, cropped spoon, bent handle, enlarged spoon bowl, shifted object, motion blur, shadow, reflection plane, or scenery.
```

三张绿幕中间图均在转换、检查和记录哈希后移除；仓库只保留 RGBA 修复板。
