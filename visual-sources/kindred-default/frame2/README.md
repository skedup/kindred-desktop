# FRAME2 draw source

This directory contains the non-runtime authoring source for the `draw`
vertical slice in `visual-packs/kindred-default`.

## Current source contract

- `keys/draw-key.png` remains the reviewed 1024×1536 RGBA authority for every
  normally visible pixel.
- `layers/draw/layers.json` is the single FRAME2-B2a-R1 layer manifest. It names
  15 ordered source/render layers, their roles, pivots, neutral visibility, and
  whether they participate in the Blender rig.
- `layers/draw/plates/` contains three repair-only plates: head/drawing-side
  hidden surfaces, support-side hidden surfaces, and a localized closed-eye
  state. Their generation prompts and boundaries are recorded beside them.
- `layers/draw/generated/` contains the deterministic provenance partition plus
  the lossless `character_surface` render composite built from it.
- `frame2-draw-rig.blend` stores the inspectable multi-object rig generated from
  those layers.
- Runtime output remains 24 frames at 512×768 RGBA / 6 FPS. The desktop runtime
  does not read source layers, Blender data, or repair plates. Blender output is
  re-encoded by the project PNG codec so unchanged pixels also produce unchanged
  committed bytes.

The visible-pixel partition is lossless: each reviewed source pixel belongs to
exactly one neutral layer. The repair underlay is sampled only beneath the
head/hair/eye, drawing-arm/brush, and support-side motion regions. This lets
motion reveal filled surfaces without replacing the approved character art.
Validation re-derives every generated layer from the key and repair plates and
requires a byte-for-byte match, so either source changing without a rebuild
fails closed.

FRAME2-B2a-R1 is a **continuous-surface frame rig**, not a complete Live2D
master. Fine-grained body, sleeve, arm, and palette layers remain in the source
partition for provenance and semantic validation, but they are not rendered as
separate alpha planes. They are losslessly recomposed into one
`character_surface` mesh, eliminating the internal shoulder/elbow/wrist cuts
that remained visible in the rejected B2a cut-out experiment. Head/face,
open/closed eyes, front/back hair, brush, fixed props, and repair underlay stay
independent because they have genuine overlap or state boundaries. The current
surface is suitable for pre-rendered frames; it is deliberately not labelled
Live2D-ready.

## Motion

The four-second loop is `observe → short stroke → withdraw → localized blink
and slight head tilt → return`. Head and eye layers share a pivot; front/back
hair add restrained delayed follow; the brush follows the drawing wrist. One
continuous displacement field drives torso breathing, both shoulder → elbow →
wrist chains, both translucent sleeves, the support hand and its palette. Since
all of those pixels share one mesh, their motion blends spatially rather than
meeting at transparent layer edges. The camera, chair/easel anchors,
crossed-leg silhouette, and boot baseline remain fixed. The first four observe
frames are the one-shot `enter`; the loop then rotates through all 24 frames
without duplicating a seam frame.

## Rebuild and validation

```bash
python -m tools.visual_pipeline.draw_layers_build --repository-root "$PWD"
python -m tools.visual_pipeline.draw_layers_validate --repository-root "$PWD"

"$HOME/Library/Application Support/Steam/steamapps/common/Blender/Blender.app/Contents/MacOS/Blender" \
  --background \
  --python tools/visual_pipeline/draw_generate.py \
  -- \
  --repository-root "$PWD"

python -m tools.visual_pipeline.draw_validate
python scripts/validate_visual_pack.py visual-packs/kindred-default
```

The source brief, acceptance criteria, and remaining production work live in
[`docs/discussions/2026-08-20-frame2-layered-draw-production.md`](../../../../docs/discussions/2026-08-20-frame2-layered-draw-production.md).
