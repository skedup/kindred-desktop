# Desktop visual pipeline

This package owns offline production and validation for Kindred desktop-spirit
frame assets. It is developer tooling: the shipped desktop runtime consumes
only visual-pack manifests and rendered PNG files, and never imports Blender or
these Python modules.

## Responsibilities

- `standing_generate.py` renders the standing `settle`, `eat`, and `sleep`
  motion set through Blender and FFmpeg.
- `standing_validate.py` enforces that standing motion set's frame geometry,
  schedule, blink locality, and baseline contract.
- `draw_contract.py` defines the geometry used by the earlier FRAME2 layered
  authoring path.
- `draw_layers_build.py` deterministically partitions the reviewed `draw` key
  into FRAME2-B2a-R1 provenance layers and builds the lossless continuous
  character surface used for rendering.
- `draw_layers_validate.py` enforces layer inventory, lossless visible-pixel
  partitioning, byte-for-byte provenance from the reviewed key/repair plates,
  repair-underlay overlap, and localized eye-state contracts.
- `draw_generate.py` retains the earlier FRAME2 continuous-surface authoring
  path for comparison and source inspection.
- `draw_validate.py` retains the corresponding earlier FRAME2 validator.
- `draw_layered_generate.py` renders the production FRAME2E loop with a
  byte-stable chair/easel plate, one seamless character surface, and a rigid
  brush. The seated contact is anchored while the torso, painting arm, and
  crossed legs move; a full-loop visible-prop semantic mask is regenerated.
- `draw_layered_contract.py` owns the dependency-free 84-frame / 12 FPS timing
  contract shared by Blender authoring, tests, promotion, and validation.
- `draw_layered_promote.py` verifies the pinned approval manifest, stages the
  reviewed FRAME2E loop, and transactionally replaces the bundled runtime plus
  its 12 FPS motion manifest with rollback on failure.
- `draw_layered_validate.py` verifies source inventory, loop closure, exact
  ordered source/runtime digests, the full reviewed visible-prop mask,
  transparent corners, visible hand/body/leg motion, rigid chest and inner
  shoulder behavior, and exact source-to-runtime parity.
- `eat_layers_build.py` deterministically assembles the approved `eat-v2`
  master, hidden-surface repair plates, continuous character surface, rigid
  spoon, foreground occluder, and static-region validation masks. Its preview
  compositor replays the grip from the same continuous character surface; it
  does not create a separate limb asset.
- `eat_contract.py` owns the dependency-free 84-frame / 12 FPS / 7-second
  timing, geometry, source paths, and character replay regions for `eat-v2`.
- `eat_generate.py` renders the review loop from fixed rear/foreground props,
  one continuously deformed character surface, and one rigid spoon. The two
  depth-order replays are derived from and deformed with that same surface. It
  also renders the fixed-prop reference and derives its full-loop visible mask.
- `eat_validate.py` verifies the approved source inventory, closed loop,
  visible motion, rigid chest/shoulder behavior, fixed-prop mask, transparent
  top edge, approval digests, runtime schedule, and source/runtime parity.
- `eat_promote.py` verifies the pinned approval record, stages all 84 reviewed
  frames, and transactionally installs the runtime loop and 12 FPS manifest.
- `walk_contract.py` pins the accepted video take, 38-frame gait-cycle trim,
  12 FPS playback, chroma-key settings, and 512×768 desktop geometry.
- `walk_video_build.py` normalizes the accepted green-screen image-to-video
  take, keys and despills its translucent edges, restores the reviewed cool
  clothing palette, slows one closed gait cycle without optical-flow frames,
  and writes a centered transparent-character 512×768 review sequence adapted
  to the desktop window. It has no scenery and remains an offline build that
  does not promote runtime assets.
- `walk_validate.py` enforces the accepted 38-frame inventory, transparent
  corners, centered union bounds, grounded canvas placement, bounded body
  drift, visible motion, and restrained loop seam.
- `walk_promote.py` losslessly encodes only those accepted transparent frames
  as runtime WebP assets and installs the 12 FPS `walk` motion manifest.
- `png_rgba.py` contains the dependency-free PNG reader shared by validators.
- `blender_canvas.py` owns the transparent scene, orthographic canvas, mesh,
  material, and texture primitives shared by Blender generators.

The top-level `scripts/` directory remains reserved for independent repository,
release, deployment, CI, and diagnostic commands rather than animation-domain
implementation.

## Validation

```bash
python -m tools.visual_pipeline.standing_validate
python -m tools.visual_pipeline.draw_layered_validate
python -m tools.visual_pipeline.eat_validate \
  --source-root visual-sources/kindred-default/eat-v2 \
  --source-only
```

## Rendering

Run the generators through Blender 5.2 LTS:

```bash
Blender --background --python tools/visual_pipeline/standing_generate.py -- \
  --repository-root "$PWD"

python -m tools.visual_pipeline.draw_layers_build --repository-root "$PWD"

python -m tools.visual_pipeline.eat_layers_build --repository-root "$PWD"

Blender --background --python tools/visual_pipeline/eat_generate.py -- \
  --repository-root "$PWD"

Blender --background --python tools/visual_pipeline/draw_generate.py -- \
  --repository-root "$PWD"

Blender --background --python tools/visual_pipeline/draw_layered_generate.py -- \
  --repository-root "$PWD"

python -m tools.visual_pipeline.draw_layered_promote \
  --repository-root "$PWD"

python -m tools.visual_pipeline.eat_promote \
  --repository-root "$PWD"

python -m tools.visual_pipeline.draw_layered_validate \
  --source-root visual-sources/kindred-default/frame2e

python -m tools.visual_pipeline.eat_validate \
  --source-root visual-sources/kindred-default/eat-v2

python -m tools.visual_pipeline.walk_video_build --repository-root "$PWD"

python -m tools.visual_pipeline.walk_validate --repository-root "$PWD"

python -m tools.visual_pipeline.walk_promote --repository-root "$PWD"
```
