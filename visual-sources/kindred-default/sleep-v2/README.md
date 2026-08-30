# SLEEP-V2 source notes

状态：母版与放大动作版已批准并发布

本目录保存侧卧抱枕 `sleep` 的批准母版、确定性 Blender 动画源帧和人工验收
预览。人物、抱枕、睡裙、薄纱睡袍与双腿保持为一个连续纹理表面，不按肩、肘、
髋或膝拆分，避免关节接缝。

## Production model

- `keys/sleep-master.png` 是 1024×1536 RGBA 的唯一视觉母版；
- 不保留原始绿幕中间件，母版已通过固定 FFmpeg 参数提取真实透明通道；
- 不包含床、卧室或海报背景，只保留人物、抱枕和少量随身织物；
- `frames/scene-warp-v1/` 用整张连续网格生成 512×768、12 FPS 的闭环源帧；
- 运动由上身呼吸、抱枕轻收紧和交叠双腿的小幅调整组成，动作连续且不切片；
- `previews/sleep-v2-loop-v2.mp4` 是 512×768、12 FPS、72 帧、6 秒当前循环；
- `previews/sleep-v2-contact-sheet-v2.png` 是八个等时间点的静态检查表；
- v2 相对首版把局部呼吸与拥抱幅度提高约 40%，交叠腿调整提高约 50%，
  但仍保持外框、枕头上缘与整幅位置固定；
- 获准帧已逐像素无损 promotion 到运行时 `assets/body/sleep-v2/`，并直接替换
  旧的 6 FPS FRAME1 站姿睡眠。

## Rebuild preview

从仓库根目录执行：

```bash
"$HOME/Library/Application Support/Steam/steamapps/common/Blender/Blender.app/Contents/MacOS/Blender" \
  --background --python tools/visual_pipeline/sleep_generate.py -- \
  --repository-root "$PWD"
```

生成器只保留当前 rig，并输出透明 PNG 源帧。人工确认由这些源帧编码的循环 MP4
与接触表后，再以无损 WebP promotion 直接替换现有运行时 `sleep`，不保留非正式
兼容路径。

## Validation

```bash
python -m tools.visual_pipeline.sleep_validate --repository-root "$PWD"
```

当前验证固定 72 张源帧、512×768 RGBA、透明四角、全循环画布边界不漂移、
首尾解码像素完全一致，并确认动作峰值不同于静止帧。

## Promotion

```bash
python -m tools.visual_pipeline.sleep_promote --repository-root "$PWD"
python scripts/validate_visual_pack.py visual-packs/kindred-default
```

Promotion 把 72 张批准 PNG 源帧逐帧无损编码为 WebP，更新 `motions/sleep.json`，
并直接删除旧的 FRAME1 站姿睡眠帧；不保留运行时兼容副本。`RENDERED.txt`
固定母版、正式预览、source 帧与 runtime 帧的 SHA-256，并记录逐帧解码像素一致。
