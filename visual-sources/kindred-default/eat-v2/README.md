# EAT-V2 source notes

状态：母版与动画闸门已通过，EAT-3 已发布

本目录保存早餐桌坐姿 `eat` 的批准母版、确定性分层、Blender rig、
84 张 source 帧、人工验收预览、批准清单和固定道具验证基准。获准帧已
promotion 到运行时 visual pack 的 `assets/body/eat-v2/`。

## Production model

- `layers/rear-static/` 和 `layers/foreground-occluder/` 在全循环中固定；
- 桌面在运行时两侧各保留 17px 透明 gutter，使 304px 舞台中的桌面有效宽度
  与 284px 状态标签对齐，人物和椅子不缩放；
- `layers/character/` 是唯一连续人物表面；
- `layers/spoon/` 是围绕握点平移、旋转的刚性道具；
- `layers/generated/` 的扶碗手与握柄重放由同一人物表面确定性提取，
  只解决前后遮挡，不是额外肢体资产，也不单独驱动；
- `frames/scene-warp-v1/` 是 512×768 RGBA、12 FPS、84 帧、7 秒闭环；
- `previews/eat-v2-loop-v1.mp4` 和 `previews/eat-v2-contact-sheet-v1.png`
  是已通过动画闸门的正式预览；
- `RENDERED.txt` 固定母版、分层、预览、source 帧和运行时命名帧的 SHA-256；
- `layers/generated/eat-static-props-alpha-v1.png` 与对应 visible mask 用于
  证明椅子、桌面、碗和面包盘的可见像素在完整循环中保持稳定。

## Rebuild

从仓库根目录执行：

```bash
python -m tools.visual_pipeline.eat_layers_build --repository-root "$PWD"

Blender --background --python tools/visual_pipeline/eat_generate.py -- \
  --repository-root "$PWD"
```

生成器关闭 Blender 的编号备份，只保留当前 `eat-v2-rig.blend`。纹理边界使用
`CLIP` 而不是重复采样，避免桌面底部像素绕回透明画布顶部。

## Validation and promotion

```bash
python -m tools.visual_pipeline.eat_validate \
  --source-root visual-sources/kindred-default/eat-v2 \
  --source-only

python -m tools.visual_pipeline.eat_promote --repository-root "$PWD"

python -m tools.visual_pipeline.eat_validate \
  --source-root visual-sources/kindred-default/eat-v2
```

已确认 source 帧数量、尺寸、RGBA、上方透明边角、7 秒时间表、首尾闭环、
固定道具、人物运动和 source/runtime 一致性。旧 FRAME1 `eat` 已直接移除，
不保留运行时兼容路径或保障式构建。
