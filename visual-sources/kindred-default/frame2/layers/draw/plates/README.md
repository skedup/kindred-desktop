# FRAME2-B1 / B2a repair plates

These plates were produced with the built-in OpenAI image-edit workflow on
2026-08-21. They are not runtime assets and are never displayed as complete
frames. `draw-key.png` remains the authority for all normally visible pixels;
the plates only fill surfaces revealed by local cut-out motion.

## `hidden-clean.png`

Mode: precise object edit. The reviewed `draw-key.png` was the only input.

```text
Use case: precise-object-edit
Asset type: hidden-surface clean plate for an original VTuber desktop-spirit cut-out animation
Input image: the only edit target and the absolute authority for character identity, seated pose, camera, proportions, outfit design, materials, lighting, chair, easel, canvas, and composition.

Create a clean backing plate of exactly the same image and alignment. Remove only these foreground elements: (1) the loose front-hair strands that cross the forehead, eyes, cheeks, neck and upper torso, and (2) the character's raised drawing-side translucent sleeve, forearm, hand, slender brush, and the narrow brush overlap across the canvas. Reconstruct only the surfaces hidden immediately beneath those removed elements: complete the forehead, both eyes and eyebrows, cheeks, ear/neck edge, back hair mass, dark-teal satin bodice with its existing gold piping, and the small canvas/easel areas behind the hand and brush. Keep the support arm, palette/sketch board, crossed legs, boots, chair, easel, all other hair, clothing, jewelry, ornaments and every visible silhouette unchanged.

Preserve exact 1024x1536 portrait framing, pixel alignment, subject scale and placement. Preserve premium VTuber key-art rendering, clean anime linework, restrained painterly shading, dense dark-teal satin, iridescent lavender organza, gold botanical embroidery, dark leather, violet crystals, and the existing cool studio light. This is repair/inpainting, not a redesign.

Place the complete edited subject on a perfectly flat solid #00ff00 chroma-key background. No floor, shadow, gradient, texture, reflection, particles, scenery, text, watermark, extra props, new ornaments, anatomy changes, pose changes, camera changes, beauty retouch, mottled texture, plastic shine, duplicated limbs, duplicated brush, or cropped pixels. Do not use #00ff00 in the subject.
```

## `eyes-closed.png`

Mode: precise object edit. The reviewed `draw-key.png` was the only input.

```text
Use case: precise-object-edit
Asset type: closed-eye repair plate for an original VTuber desktop-spirit cut-out animation
Input image: the only edit target and the absolute authority for identity, pose, camera, proportions, clothing, materials, hair, chair, easel, lighting, composition and pixel placement.

Change only the eyes: close both eyes naturally with elegant relaxed upper-lid curves, preserving the original cool focused expression and exact face angle. Keep eyebrows, eyelashes, nose, lips, face shape, front-hair strands crossing the face, skin shading and every other pixel-level design element as close to the input as possible. Do not move, redesign, beautify or regenerate the character, hands, hair, clothing, chair, easel, canvas or props.

Preserve exact 1024x1536 portrait framing, subject scale, alignment and placement. Preserve premium VTuber key-art rendering, clean anime linework, restrained painterly shading and all original material detail. This is a localized eye-state edit, not a redesign.

Place the complete edited subject on a perfectly flat solid #00ff00 chroma-key background. No floor, shadow, gradient, texture, reflection, particles, scenery, text or watermark. No anatomy changes, pose changes, camera changes, new ornament, mottled texture, plastic shine, duplicated elements or cropping. Do not use #00ff00 in the subject.
```

The two FRAME2-B1 chroma-key intermediates were converted to RGBA with the
bundled `remove_chroma_key.py` helper and then removed. Only the transparent
repair plates are retained.

## `support-clean.png`

Mode: precise object edit. The reviewed `draw-key.png` was the only input. This
FRAME2-B2a plate removes only the viewer-left support assembly; the existing
`hidden-clean.png` remains authoritative for the drawing-side and head repairs.

```text
Use case: precise-object-edit
Asset type: FRAME2-B2a hidden-surface repair plate for an original VTuber desktop-spirit cut-out animation
Input image: Image 1 is the only edit target and the absolute authority for character identity, seated pose, camera, proportions, face, hair, outfit design, materials, lighting, chair, easel, canvas, composition, scale, and pixel alignment.

Primary request: remove only the support-side foreground assembly on the viewer-left side of the image: the large translucent lavender organza sleeve, its metallic upper-arm band and violet cuff, the support forearm and hand crossing the lap, and the long horizontal palette/sketch board held by that hand. Reconstruct only the surfaces immediately hidden beneath those removed elements: complete the dark-teal satin bodice and waist with existing gold piping, the purple waist straps and crystal ornament where logically continuous, the near skirt/lap and upper-thigh surfaces, and the small chair-seat or background gaps directly behind that support assembly.

Critical invariants: keep the viewer-right raised drawing sleeve, drawing forearm and hand, slender brush, head, face, eyes, all hair, jewelry, legs, thigh strap, boots, hanging embroidered fabric, chair, easel, canvas, and every other visible element unchanged. Do not move or redesign anything. Preserve the exact 1024x1536 portrait framing, original subject scale, pose, silhouette outside the removed region, and pixel placement. Preserve premium VTuber key-art rendering, clean anime linework, restrained painterly shading, dense dark-teal satin, iridescent lavender organza, gold botanical embroidery, dark leather, violet crystals, and the existing cool studio light. This is localized repair/inpainting, not a redesign or beauty pass.

Scene/backdrop: place the complete edited subject on a perfectly flat solid #00ff00 chroma-key background for local alpha extraction. The background must be a single uniform color with no shadow, gradient, texture, reflection, floor plane, particles, or lighting variation. Do not use #00ff00 anywhere in the subject.

Avoid: changes to identity, anatomy, expression, pose, camera, body proportions, clothing design outside the removed region, added ornaments, extra limbs, duplicated hands, duplicated boards, duplicated brushes, missing drawing arm, mottled or dirty texture, plastic shine, text, logos, watermark, scenery, cropping, or green spill.
```

The built-in image-edit result was converted directly from its generated
chroma-key output to this RGBA plate with the bundled helper; no raw chroma
intermediate is retained in the repository.
