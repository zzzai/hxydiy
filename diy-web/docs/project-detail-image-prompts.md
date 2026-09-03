# 荷小悦项目详情长图提示词

统一生成规则：使用 `hxy-mascot.webp` 作为唯一品牌 IP 参考图；新中式新国潮插画；竖版 1024x1536；画面分成上、中、下三个连续视觉段落但不要生成文字；留出干净留白；不生成中文、价格、Logo、按钮、二维码、水印；不改变 IP 的脸型、帽子、服装和比例；避免医疗暗示、夸张疗效、人物肢体畸形和杂乱道具。生成后由前端叠加项目名称、时长、价格和选项说明。

## hxy-qiqing-30 草本泡脚

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: create a calm new-Chinese herbal foot-bath story image using the provided 荷小悦 mascot as a fixed brand character. Scene/backdrop: warm white and dark herbal green interior, carved wood foot bath area, fresh ginger, chenpi, mugwort and five-elements tea arranged naturally. Composition/framing: continuous vertical three-part composition, mascot preparing the herbal liquid at the top, feet soaking and steam in the middle, tea and quiet rest at the bottom, clear negative space for UI copy. Lighting/mood: warm morning light, clean, reassuring, unhurried. Constraints: preserve mascot identity and proportions, no text or symbols.

## hxy-xiangxiang-60 草本沐足 60 分钟

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: show a fuller herbal foot and leg relaxation experience using the fixed 荷小悦 mascot. Scene/backdrop: new-Chinese foot-care chair, wooden screen, herbal basin, folded towel. Composition/framing: top shows preparation, middle shows gentle foot and calf care, bottom shows warm tea and relaxed posture; vertical continuity and generous white space. Lighting/mood: soft jade-green and wood tones, warm diffused light, comfortable and professional. Constraints: no text, no price, no medical claims, preserve mascot.

## hxy-xiaoqi-90 招牌草本沐足 90 分钟

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: premium signature herbal foot-care journey using the fixed 荷小悦 mascot. Scene/backdrop: refined new-Chinese room, herbal basin, bamboo tools, hot herbal compress, quiet tea table. Composition/framing: three connected moments: herbal preparation, signature care details, spacious final relaxation; editorial vertical composition. Lighting/mood: deep herbal green, restrained warm gold, calm premium hospitality. Constraints: no text or pricing, no extra characters, preserve mascot identity.

## hxy-tuina-70 推拿 70 分钟

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: communicate professional body relaxation and careful technique without medical claims. Scene/backdrop: clean new-Chinese treatment room, wooden bench, folded linen, subtle botanical elements. Composition/framing: mascot in three connected poses suggesting shoulder, back and leg relaxation, never showing invasive anatomy. Lighting/mood: soft directional light, dark green, warm white and wood. Constraints: no text, no watermark, no medical symbols, preserve mascot.

## hxy-spa-90 SPA 90 分钟

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: premium botanical oil relaxation experience using the fixed 荷小悦 mascot. Scene/backdrop: calm spa room, three classic oil cues represented only by amber bottles and botanicals, folded towels, ceramic tray. Composition/framing: oil selection atmosphere at top, gentle care moment in middle, quiet recovery at bottom. Lighting/mood: soft warm light, restrained jade green and warm gold, clean luxury. Constraints: no text or labels on bottles, no medical claims, preserve mascot.

## hxy-jubu-30 局部调理 30 分钟

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: show focused, customer-chosen local relaxation for shoulder, waist-hip, legs, abdomen and feet. Scene/backdrop: modular new-Chinese wellness room with five subtle visual cues, not a collage. Composition/framing: flowing top-to-bottom path from shoulder to feet with mascot guiding attention; clean separation and whitespace for selectable options. Lighting/mood: clear, reassuring, practical and warm. Constraints: no anatomy diagrams, no text, preserve mascot.

## hxy-baguan-1 拔罐

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: gentle cupping add-on atmosphere, tasteful and non-medical. Scene/backdrop: bamboo tray, clean glass cups, towel and herbal accents in a new-Chinese room. Composition/framing: tool preparation, careful service suggestion, relaxed finish. Lighting/mood: warm, clean, professional. Constraints: no bruising, no medical claims, no text, preserve mascot.

## hxy-guasha-1 刮痧

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: gentle gua-sha add-on atmosphere with a jade tool and herbal oil. Scene/backdrop: clean wood and jade setting, folded towel, botanical detail. Composition/framing: preparation, careful motion implied without close-up injury, calm finish. Constraints: no redness or injury, no text, preserve mascot.

## hxy-caier-30 采耳 30 分钟

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: refined ear-care relaxation scene using the fixed mascot. Scene/backdrop: quiet new-Chinese lounge chair, delicate tools, cotton, warm lamp. Composition/framing: preparation, comfortable reclined moment, tea and rest. Constraints: no invasive close-up, no text, preserve mascot.

## hxy-head-30 头疗 30 分钟

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: head and scalp relaxation atmosphere, not medical treatment. Scene/backdrop: herbal towel, wooden comb, botanical steam and comfortable chair. Composition/framing: preparation, gentle head-care silhouette, quiet finish. Lighting/mood: warm, restful, clean. Constraints: no medical claims, no text, preserve mascot.

## hxy-taoke-60 固定套盒

Use case: illustration-story. Asset type: mobile service detail long image. Primary request: a composed fixed herbal wellness set presented as a complete experience. Scene/backdrop: premium new-Chinese tray with coordinated herbal products, towel and tea; no individual price labels. Composition/framing: complete set at top, service atmosphere in middle, finished rest at bottom. Constraints: no text, no price, no invented product packaging, preserve mascot.

## 拼接与前端编排

每张生成图作为一个移动端详情视觉模块使用，不把可变文字烘焙进图片。若单张长图出现主体或留白不稳定，按同一提示词拆成三个 1024x512 横向段落后由前端纵向拼接；项目名称、时长、价格、必选项、可选项、优惠和线下结算说明继续使用真实数据模块渲染。
## 统一视觉迭代（2026-08-20）

上一版招牌草本沐足采用浅底新中式水彩插画，不使用摄影感、深色室内场景或泛荷塘氛围。后续项目统一沿用这一风格：荷小悦 IP 固定、宣纸感暖白底、淡草本绿、自然木色、细线手绘、三段连续叙事。

通用提示词：

```text
Use case: illustration-story. Asset type: mobile service detail long image. Use the provided 荷小悦 mascot as a fixed brand character. Create a gentle refined Chinese ink-and-watercolor new-Chinese illustration in a continuous three-panel vertical composition, matching the reference visual style: white paper background, soft pale herbal green washes, delicate hand-drawn linework, natural wood and bamboo, restrained warm gold, generous white space. Preserve mascot face, green leaf hat, clothing and proportions. No Chinese text, numbers, price, logo, watermark, medical claims or extra characters.
```

项目差异只写在通用提示词之后：先呈现准备体验，再呈现核心服务，最后呈现放松收尾。文字、价格、时长、优惠和按钮全部由前端真实数据渲染，图片仅承担项目识别和体验想象。
