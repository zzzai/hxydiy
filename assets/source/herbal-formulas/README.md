# 五方插画本地预览记录

2026-09-14 使用内置 image_gen 分别生成五张独立透明底插画。用户已确认三味药材与同屏五标签方案；素材用于卡片示意，不用于药材鉴别。原 PNG 按明确文件名纳入本目录版本归档，运行素材为 `diy-web/public/assets/herbal/formula-*.webp`。

| 文件 | 用户确认的三味药材 |
| --- | --- |
| formula-wood | 玫瑰花、佛手、合欢皮 |
| formula-fire | 桂枝、丹参、鸡血藤 |
| formula-earth | 茯苓、薏苡仁、陈皮 |
| formula-metal | 桑叶、菊花、百合 |
| formula-water | 杜仲、桑寄生、淫羊藿 |

共同生成提示词（各方将 subject 替换为上表药材及外形描述）：

> Generate a single standalone botanical watercolor asset for a refined Chinese herbal foot-soak UI. Exactly three ingredients: subject. Each ingredient recognizable, natural grouped arrangement, low and wide 1.8:1 cluster centered on 3:2 landscape canvas with 7% padding. Fine hand-painted natural wood brown and muted green, semi-realistic delicate illustration. Transparent background if supported, otherwise pure white. NO text, no labels, no UI, no borders, no container, no extra herbs, no people, no watermarks. Final rendered slot 220 by 130 px; keep the group wide and crisp. Pure illustrative ingredient art.

本地转换保留透明通道、完整比例，输出 660×391 WebP，quality=88；原图 SHA-256 见 `MANIFEST.sha256`。首次批量连接失败后重试成功，没有覆盖既有生产素材。
