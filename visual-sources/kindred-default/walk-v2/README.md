# walk-v2 accepted source

This directory contains the accepted transparent walking loop used to build the
Kindred desktop `walk` motion. The character is original first-party Kindred
artwork; no scenery is included in the promoted runtime asset.

## Source and build

`video-source/walk-character-green-v1.mp4` is the reviewed image-to-video take.
The deterministic offline build:

1. samples the source at 16 FPS;
2. selects frames `[20, 58)` as one closed 38-frame gait cycle;
3. removes the green plate and despills translucent edges;
4. restores opaque skin, hair, and dress materials while preserving graduated
   antialiased and sheer silhouette pixels;
5. restores the reviewed deep teal/violet clothing with a cool-hue-only grade;
6. uniformly adapts the square source to a centered 512×768 transparent canvas.

Run the build with:

```bash
python -m tools.visual_pipeline.walk_video_build --repository-root "$PWD"
```

The accepted source outputs are:

- `frames/video-character-v1/`: 38 centered transparent PNG frames;
- `previews/walk-v2-transparent-loop-v3.mp4`: dark-matte motion preview;
- `previews/walk-v2-transparent-contact-sheet-v3.png`: compact frame review.

The portrait adaptation scales uniformly and crops only lateral transparent
space. It does not stretch the character. The raw video, its audio, and the
non-looping head and tail are source material and are not bundled with the
desktop application.

## Night backdrop

`environment/walk-night-v1.png` is the reviewed first-party environment source.
The runtime pack contains one 512×768 static derivative at
`assets/backgrounds/walk-night-v1.png`. Deterministic alpha masks keep the
desktop visible, retain one stronger near-building slice at the extreme right,
and fade a quieter distant skyline before the character's lower body. No road
or ground plane is retained. The backdrop is rendered once behind the 38-frame
body loop, so it does not drift between frames or duplicate scenery bytes in
every frame.
`previews/walk-v2-night-layer-preview.png` and
`previews/walk-v2-night-layer-loop.mp4` record the reviewed runtime order of
backdrop, body frames, and existing walk decoration on a dark QA matte.

## Validation and runtime promotion

Validate the accepted PNG sequence, then losslessly encode it as runtime WebP:

```bash
python -m tools.visual_pipeline.walk_validate --repository-root "$PWD"
python -m tools.visual_pipeline.walk_promote --repository-root "$PWD"
```

Promotion installs 38 WebP frames under
`visual-packs/kindred-default/assets/body/walk-v2/` and writes the 12 FPS
`visual-packs/kindred-default/motions/walk.json` manifest.
