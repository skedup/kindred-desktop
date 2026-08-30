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
4. restores the reviewed deep teal/violet clothing with a cool-hue-only grade;
5. uniformly adapts the square source to a centered 512×768 transparent canvas.

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

## Validation and runtime promotion

Validate the accepted PNG sequence, then losslessly encode it as runtime WebP:

```bash
python -m tools.visual_pipeline.walk_validate --repository-root "$PWD"
python -m tools.visual_pipeline.walk_promote --repository-root "$PWD"
```

Promotion installs 38 WebP frames under
`visual-packs/kindred-default/assets/body/walk-v2/` and writes the 12 FPS
`visual-packs/kindred-default/motions/walk.json` manifest.
