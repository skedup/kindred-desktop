# `sleep-v2` 获准母版生成记录

状态：已批准
日期：2026-08-29
批准：用户明确认可最终人物、睡裙、抱枕、交叠双腿与无床构图

## 输出

- 获准 RGBA 母版：`sleep-master.png`
- 尺寸：1024×1536
- Alpha：有
- SHA-256：`c3698c8ddb16f38a9c8e647ffe00c15656f0c42af8d74aabd1a74cf885a7a318`
- 原始绿幕输出 SHA-256：`b872e44621d5df0dd75c909a541e2fd690a1b68118b580d7f3119b39632ce254`
- 512×768 透明预览：`../previews/sleep-master-512x768.png`
- 预览 SHA-256：`a0477619c8458f602a4d12e2dd7e1ecf8b0362744a003a7ec1486c66061cc586`

## 输入职责

1. `visual-sources/kindred-default/frame1/keys/sleep.png`
   - 原设人物身份、五官、发型、发色、紫晶发饰与整体气质的唯一权威；
   - 生成时只使用该图头部区域的 700×700 临时裁剪，未把旧站姿和服装作为姿态参考。
2. 不使用此前的 AI 睡眠概念图作为输入。
   - 最终母版从原设身份参考与文字构图约束重新生成，避免多次 AI 图参考带来的鱼鳞纹理与身份漂移。

## 提示词

```text
Use case: identity-preserve
Asset type: new from-scratch concept key art for a VTuber desktop-spirit sleep animation, portrait 2:3.
Input image: the only identity reference. Preserve this original adult woman's facial structure, closed-eye shape, eyebrows, nose, mouth, pale skin tone, mature restrained expression, deep-indigo side-bun hairstyle, teal inner highlights, shoulder/upper-chest-length loose strands, purple crystal hair ornament and refined temperament. Do not copy the standing pose, clothing, black background or body rendering.
Primary request: create a completely new anatomically believable side-sleeping pose. She lies diagonally on her side while embracing one soft ivory pillow. Her full legs and both bare feet are visible rather than hidden under a duvet. The lower/rear leg extends naturally downward on a relaxed diagonal with only a slight knee bend. The upper/front leg bends moderately at the hip and knee and rests across the lower leg. The ankles overlap gently near the lower portion of the composition; both feet are relaxed, distinct and anatomically correct. This is a calm sleeping leg-cross, not a tightly curled fetal pose.
Anatomy and proportions: elegant adult proportions around 7.5 heads tall; pelvis, thighs, knees, calves, ankles and feet preserve realistic relative lengths; thighs must not be shortened; knees must be clearly separated and correctly placed; calves taper naturally; both feet have coherent heel, arch, instep and five toes. Use only mild three-quarter-overhead foreshortening, with no fisheye distortion and no oversized foreground knee. The visible leg length must balance the torso and occupy enough of the canvas to read clearly.
Sleepwear: a refined midnight-teal silk nightgown ending around mid-thigh, comfortable and sophisticated, softly draped neckline, slender straps, restrained lavender lace edging and one small amethyst pendant. A loose translucent lavender chiffon sleep robe rests around the arms and trails lightly beside the hips. The gown covers the pelvis and underwear completely; elegant rather than lingerie-only.
Blanket treatment: no bed or mattress. If any blanket is present, retain only a small irregular deep-indigo/lavender fabric fold behind the hips or beneath part of the torso as secondary support. It must not cover the knees, calves, ankles or feet, and must not form a circle or cocoon.
Materials: exquisite premium silk and chiffon with broad coherent highlights, believable fabric weight, clean satin sheen, fine lace edges, limited delicate gold botanical embroidery only at selected borders, and sharply defined amethyst accents. Large clean tonal regions, controlled folds, no noisy microtexture.
Composition/framing: three-quarter overhead perspective, diagonal elongated S-shaped sleeping silhouette centered in a portrait 2:3 canvas. Include the entire head, torso, both legs and both feet with 8–10% margin and no clipping. Both natural five-finger hands embrace the pillow. Suitable for later animation-layer extraction and subtle leg movement.
Lighting: soft warm amber light on face and pillow, cool blue-violet rim light on hair, robe and legs; subject lighting only.
Background: perfectly uniform flat chroma-key green #00FF00 edge to edge, no gradient, vignette, shadow, texture, checkerboard, scenery or dark corners, and no green spill on the subject.
Style: premium original anime VTuber key visual, refined clean linework, controlled painterly shading, mature and graceful.
Constraints: identity remains recognizably the same as the reference; hair does not extend past upper chest or spread under the body; no bed, room, platform, text, logo or watermark; both legs and feet must be fully readable.
Avoid: fetal ball pose, both knees pulled to chest, shortened thighs, giant knees, tiny calves, twisted pelvis, fused legs, missing leg, merged ankles, duplicated feet, malformed toes, stiff pointed feet, standing pose, pin-up pose, exposed underwear, excessive cleavage, waist-length hair, circular blanket nest, fish-scale texture, mottled cloth, glitter noise, plastic gloss, extra limbs or fingers.
```

## 转换记录

- 内建图像生成输出为 1024×1536 不透明绿幕 PNG；
- 使用 FFmpeg `chromakey=0x00ff00:0.20:0.035,despill=green:mix=0.35,format=rgba`
  转换为获准 RGBA 母版；
- 检查确认头发、半透明睡袍、手指、脚趾和丝绸边缘没有明显误切或绿色晕边；
- 原始绿幕文件只保留在生成缓存中，不是项目依赖，也不作为回滚资产提交。
