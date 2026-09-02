# settle-v2 source

`settle-v2` adds an occasional butterfly encounter to the standing `settle`
state. The accepted green-screen take lives in `video-source/`; generated PNG
frames and previews are reproducible review artifacts, while the promoted
visual pack contains only lossless runtime WebP frames.

The runtime plays the accepted ten-second event once, returns to the existing
slow breathing/blinking loop, then waits a random 12–28 seconds before it may
replay the event at an idle-loop boundary. This keeps the desktop spirit alive
without making the butterfly feel mechanical or interrupting a breath cycle.

Build, validate, and promote from the repository root:

```bash
python -m tools.visual_pipeline.settle_video_build --repository-root "$PWD"
python -m tools.visual_pipeline.settle_validate --repository-root "$PWD"
python -m tools.visual_pipeline.settle_promote --repository-root "$PWD"
```
