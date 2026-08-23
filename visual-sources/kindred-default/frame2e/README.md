# FRAME2E layered draw production source

This directory is the reviewed production source for the bundled `draw`
motion. It keeps environmental geometry stable while retaining a seamless
character silhouette:

- `layers/draw-static-props-alpha-v1.png`: fixed chair, easel, and canvas;
- `layers/draw-static-props-visible-mask-v1.png`: reviewed semantic mask for
  every prop pixel that remains unobscured throughout the full loop;
- `keys/stable-alpha/key-00.png`: complete character surface;
- `layers/generated/draw-character-focused-alpha-v2.png`: deterministic
  focused-eye character surface used by the rig;
- `layers/generated/draw-brush-alpha-v1.png`: rigid brush extracted from the
  same approved source;
- `frames/scene-warp-v5/`: deterministic composition over the fixed prop plate.
- `RENDERED.txt`: immutable approval manifest with input, source-loop, and
  runtime-loop SHA-256 identities.

The seven-second loop runs at 12 FPS. It makes a measured reach until the brush
contacts the canvas, completes one restrained stroke, returns, and rests. The
chest remains a stable core while the shoulder-to-wrist chain carries the
larger painting motion; the head, crossed legs, and boot tips provide a small
counter-motion. A lower-right canvas-facing pupil accent and five-degree head
inclination direct the gaze toward the brush contact without changing the
approved face. No generated intermediate frame or optical-flow interpolation
is used.

The local directory may also contain prompt experiments, superseded frame
sequences, audit images, previews, and Blender backups. `.gitignore` is an
explicit production allowlist: only the inputs above, the final 84-frame loop,
the inspectable rig, and this documentation are repository artifacts.

## Authoring prompts

The prop plate was produced by editing the reviewed seated-painting composition:

> Remove the woman, palette, paintbrush, and every loose character fragment.
> Preserve one ornate navy chair on the left and one wooden easel with blank
> canvas on the right at exactly the same scale and perspective. Uniform pure
> green background, no shadows, no extra objects, complete uncropped props.

The character key sheet was produced from the approved original character
identity and the reviewed seated-painting action:

> Character only, no chair, easel, canvas, floor, or shadows. Preserve the
> approved face, amber eyes, navy-to-teal hair, floral ornament, dark teal and
> gold dress, translucent lavender sleeves, palette, and embroidered over-knee
> boots. Four 2x2 keys of one slow elegant painting motion. Complete hands in
> every panel; stable hips, legs, face, scale, and camera; uniform green field.

One follow-up edit reduced the pose differences to a small shoulder, elbow,
wrist, and brush-tip progression. The final runtime candidates use only the
first complete key and deterministic continuous deformation.

## Rebuild

```bash
Blender --background --python tools/visual_pipeline/draw_layered_generate.py -- \
  --repository-root "$PWD"
```

The rebuild also regenerates the full-loop visible-prop mask. It intentionally
does **not** rewrite `RENDERED.txt`: after visual approval, update the pinned
digests in that file as an explicit review action, then run the validator.

## Publish into the bundled pack

The promotion step first verifies every pinned digest, stages all 84 reviewed
source frames and the manifest, then swaps the runtime directory with rollback
protection. It never rewrites the approval manifest.

```bash
python -m tools.visual_pipeline.draw_layered_promote \
  --repository-root "$PWD"

python scripts/validate_visual_pack.py \
  visual-packs/kindred-default --repository-root .

python -m tools.visual_pipeline.draw_layered_validate
```
