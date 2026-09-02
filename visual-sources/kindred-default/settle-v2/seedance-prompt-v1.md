# Settle v2 — butterfly encounter

## Recommended generation settings

- Mode: strict first-frame image-to-video with an additional pose reference
- Duration: 10 seconds
- Aspect ratio: 2:3 when available, otherwise 9:16
- Camera: fixed
- Shot: full body, single continuous take
- Background: uniform chroma green (`#00FF00`), without floor or shadow
- End frame: when supported, reuse the same neutral settle image as the end frame

## Prompt

```text
【总体目标】
以图片1作为严格首帧，参考图片2生成一段10秒、单镜头、完整连续的优雅站姿动画。图片1是自然站立的开始姿势，第一帧必须与图片1完全一致；图片2只用于锁定“蝴蝶停在抬高手上”的中段动作、手势、角色身份、服装细节、材质和精致画风，不得把图片2误当成首帧。严格保持两张图片中的同一原创成年女性角色身份、五官、紫黑色侧盘发与青绿色内层发丝、琥珀色眼睛、修长匀称的成年身材比例、深青色高领短裙、半透明淡紫灯笼袖、紫色水晶饰件、金色植物刺绣、不对称薄纱垂片与过膝高跟靴。保持精致的高端 VTuber 厚涂质感，不得重新设计角色。

【画面与机位】
全身完整入镜，从头发顶部到两只鞋跟都不能裁切。人物位于画面中央略偏右，为人物右侧抬手和蝴蝶飞行在画面左侧留下空间。固定机位，摄影机完全不移动：禁止推拉、摇移、平移、旋转、缩放、景深变化和画面整体漂移。人物脚底位置和整体尺度始终固定。背景始终是均匀纯净的高饱和绿色 #00FF00，不出现地面、投影、渐变、纹理、景物、光斑、文字或其他物体。

【动作节拍】
0.0—1.5秒：人物自然站立，重心轻微落在一条腿上，姿态松弛、舒展而优雅。呼吸起伏清晰但自然，肩颈与腰部随呼吸产生柔和联动；头发末端、透明袖口和侧裙薄纱产生可见而流畅的延迟摆动，身体不能机械摇晃或整块平移。

1.5—3.2秒：一只小型紫蓝色蝴蝶从画面左上方以轻盈、柔和的 S 形轨迹飞近。人物先被它吸引，眼睛随之明亮并主动追随，再自然转头，肩颈与上身随视线轻微展开。她将右臂向身体右外侧，也就是画面左侧，流畅而舒展地抬起：动作由肩部自然发起，肘部弯曲并低于手，前臂斜向上，手抬到肩部附近，手腕放松。手掌大体向下并略微侧转，食指优雅向外伸出，中指轻轻跟随，无名指和小指自然收拢，拇指放松。手臂和躯干之间始终有清晰空隙，手不能放到胸前。抬手幅度应当清晰可读，不要缩成谨慎的小动作。

3.2—4.2秒：蝴蝶减速并轻巧停落在抬起手的手背、靠近食指根部的位置。蝴蝶必须与手背明确接触，不得悬空，不得穿过手指。手和前臂在落下瞬间仅有极轻微的承接反应，随后稳定。

4.2—6.8秒：人物带着灵性和鲜活的兴趣观察手上的蝴蝶。脸朝向手，双眼瞳孔始终准确注视蝴蝶，不看镜头。眼神明亮、有回应，眉眼柔和舒展，嘴角带一丝自然流露的愉悦；不能呆滞、冷淡或像在审视标本，也不能夸张卖萌。她自然眨眼一次，随后略微侧头，肩颈打开，上身因好奇而产生轻柔前倾，再舒展地恢复；呼吸始终可见且连贯。蝴蝶缓慢开合翅膀两至三次，但身体仍稳稳停在手背。另一只手自然垂落，腰肩、发丝、透明袖子和侧裙薄纱保持柔和而富有生命感的联动。

6.8—8.2秒：蝴蝶从手背轻轻起飞，沿人物右外侧、即画面左侧向上画出一条舒缓弧线。人物的眼睛立即追随，随后头部、肩颈和上身产生连贯而优雅的跟随动作；抬起的手掌自然向上送出一小段距离，手指舒展开来，像是本能地送别，但不能抓握蝴蝶。动作幅度应当优雅且明确，不要只做难以察觉的微动作。

8.2—10.0秒：蝴蝶飞出画面并消失。人物仍带着明亮而舒展的神态目送它离开，目光在蝴蝶消失的位置停留片刻，再从容地放下右手，准确恢复图片1中的自然站姿、人物位置、身体尺度和呼吸状态。末帧尽量接近图片1，方便形成平滑循环。头发、透明袖子与侧裙薄纱依照手臂下落产生清晰、流畅而真实的惯性，随后柔和收束。

【动作气质】
所有动作从容、连贯、优雅、成熟、灵动而舒展。动作幅度中等且清晰可读，不能过于克制，也不能只有几乎看不见的微动作。眼神先于头部，头部带动肩颈和上身，手臂运动由肩关节自然发起，衣料与发丝随后产生柔和惯性。整体像一次自然流露的惊喜与相遇，不是机械摆臂，不是舞蹈，也不是卖萌。蝴蝶是唯一叙事焦点。

【结构与材质约束】
始终保持同一人物、同一张脸、同一发型、同一服装、同一身体比例和同一画风。肩膀、胸部、上臂、肘部、前臂、手腕与手必须保持稳定且符合人体结构；抬手时肩部不得隆起或塌陷，胸部不得被手臂挤压、拉伸或变形，袖子不得断裂、粘连或穿模。每只手始终只有五根手指，手指长度和关节自然。头发和衣料只能产生局部惯性，禁止整个人物像纸片一样整体摆动。靴子和双脚固定，不滑动、不缩放、不变形。

【蝴蝶约束】
全程只有一只蝴蝶，体型小巧，紫色与青蓝色翅膀，轮廓清晰、拍翼自然。不得复制、变大、变成发光精灵、留下夸张粒子尾迹，也不得遮挡人物五官。

【严格禁止】
禁止角色换脸、改变年龄、改变发色、改变服装、改变身材、改变鞋子；禁止多余人物、多余手臂、多余手指、多只蝴蝶；禁止手臂穿过胸部、手放胸前、蝴蝶悬空、目光看镜头；禁止镜头运动、构图漂移、人物缩放、背景变化、地面和投影；禁止文字、水印、边框、闪烁、强运动模糊、重影、局部融化、肢体消失和帧间材质跳变。
```

## Input image roles

1. `keys/settle-neutral-first-frame-green-v1.png`: upload as the strict first frame. This is a 1024×1536 chroma-green upload derivative of the existing transparent settle frame.
2. `keys/settle-butterfly-observe-green-v1.png`: upload as an additional character/action reference, not as the first frame. It is the chroma-green upload derivative of the accepted keyframe.

The original transparent settle source remains at `keys/settle-neutral-first-frame.png`, and the accepted unmodified concept remains at `keys/settle-butterfly-observe-v1.png`. If the product accepts only one input image, use the green neutral settle image as the strict first frame and rely on the detailed hand-pose instructions in the prompt. Do not use the butterfly-observation keyframe as the strict first frame, because the arrival and hand-raising beats occur before it.
