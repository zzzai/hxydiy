import QRCode from 'qrcode';

const WIDTH = 1080;
const HEIGHT = 1440;
const OUTPUT_SCALE = 0.9;
const MASCOT_URL = '/assets/ip-paopao-footbath-v3.png';
const INK = '#145545';
const PAPER = '#FBFAF5';
const OFFER_TOP = 1013;
const MUTED = '#65786B';
const FONT = '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "WenQuanYi Zen Hei", sans-serif';

function escapeStoreName(value: string) {
  return value.replace(/^荷小悦[-·]?/, '').replace(/^草本泡脚[（(]?/, '').replace(/[）)]$/, '') || '本店';
}

async function loadImage(source: string): Promise<HTMLImageElement> {
  const image = new Image();
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () => reject(new Error('海报素材加载失败'));
    image.src = source;
  });
  return image;
}

async function imageToPngDataUrl(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) throw new Error('海报素材加载失败');
  const blob = await response.blob();
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('海报素材加载失败'));
    reader.readAsDataURL(blob);
  });
}

function text(context: CanvasRenderingContext2D, value: string, x: number, y: number, size: number, color = INK, weight = 400, align: CanvasTextAlign = 'left') {
  context.font = `${weight} ${size}px ${FONT}`;
  context.fillStyle = color;
  context.textAlign = align;
  context.textBaseline = 'top';
  context.fillText(value, x, y);
}

export async function createCouponPoster(link: string, storeName: string): Promise<string> {
  // Use whole pixels per QR module, including the four-module quiet zone.
  const qrModules = QRCode.create(link, { errorCorrectionLevel: 'M' }).modules.size;
  const qrScale = Math.max(1, Math.floor(284 / (qrModules + 8)));
  const [mascotUrl, qrUrl] = await Promise.all([
    imageToPngDataUrl(MASCOT_URL),
    QRCode.toDataURL(link, {
      scale: qrScale,
      margin: 4,
      errorCorrectionLevel: 'M',
      color: { dark: INK, light: PAPER },
    }),
    document.fonts.ready,
  ]);
  const [mascot, qr] = await Promise.all([loadImage(mascotUrl), loadImage(qrUrl)]);
  const store = escapeStoreName(storeName);
  const singleClaim = new URL(link).searchParams.get('c')?.startsWith('p.') === true;
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(WIDTH * OUTPUT_SCALE);
  canvas.height = Math.round(HEIGHT * OUTPUT_SCALE);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('海报生成失败');
  context.scale(OUTPUT_SCALE, OUTPUT_SCALE);

  context.fillStyle = PAPER;
  context.fillRect(0, 0, WIDTH, HEIGHT);

  // A quiet lotus-green backdrop anchors the newly rendered mascot.
  const glow = context.createRadialGradient(790, 690, 60, 790, 690, 470);
  glow.addColorStop(0, '#E4EDDC');
  glow.addColorStop(0.72, '#EEF3E7');
  glow.addColorStop(1, PAPER);
  context.fillStyle = glow;
  // End the entire hero background at the same divider as both offer columns.
  context.fillRect(350, 240, 730, OFFER_TOP - 240);

  text(context, '荷小悦', 72, 64, 54, INK, 700);
  text(context, '®', 246, 64, 16, INK);
  text(context, '家门口的养生小馆', 74, 132, 22, MUTED);
  text(context, '草本泡脚', 1008, 86, 25, INK, 500, 'right');
  context.fillStyle = '#A86D23';
  context.fillRect(72, 208, 40, 3);

  text(context, '累了，', 72, 260, 76, INK, 600);
  text(context, '就来荷小悦', 72, 356, 76, INK, 600);
  text(context, '草本现煮', 76, 500, 28, '#A86D23', 500);
  text(context, '温暖放松', 76, 544, 28, '#A86D23', 500);
  text(context, '一桶草本热水，', 76, 642, 23, MUTED);
  text(context, '把今天的疲惫泡掉。', 76, 680, 23, MUTED);

  // Preserve the character proportions instead of stretching the reference art.
  const scale = Math.min(780 / mascot.naturalWidth, 780 / mascot.naturalHeight);
  const imageWidth = mascot.naturalWidth * scale;
  const imageHeight = mascot.naturalHeight * scale;
  context.drawImage(mascot, 288 + (780 - imageWidth) / 2, 246 + (780 - imageHeight) / 2, imageWidth, imageHeight);

  context.fillStyle = '#E2E8DC';
  context.fillRect(72, OFFER_TOP, 936, 1);
  text(context, '半价放松，慢慢享受', 76, 1045, 24, MUTED);
  text(context, '全场', 76, 1106, 38, INK, 500);
  text(context, '5', 180, 1082, 126, INK, 600);
  text(context, '折', 264, 1133, 52, INK, 500);
  text(context, '小项除外', 78, 1284, 22, MUTED);
  text(context, '领取后 60 天有效', 78, 1322, 21, '#A86D23');
  if (singleClaim) text(context, '仅 1 张 · 登录领取 · 绑定本人', 78, 1358, 18, MUTED);

  const qrX = Math.round(856 * OUTPUT_SCALE - qr.naturalWidth / 2);
  const qrY = Math.round(1226 * OUTPUT_SCALE - qr.naturalHeight / 2);
  // Match the paper background while preserving the four-module quiet zone.
  // Draw the QR at native output pixels so resizing never blurs its modules.
  context.save();
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.imageSmoothingEnabled = false;
  context.drawImage(qr, qrX, qrY);
  context.restore();
  text(context, '扫码领取半价券', 856, 1045, 24, INK, 500, 'center');

  text(context, `荷小悦 · ${store}`, 72, 1390, 19, INK, 500);
  text(context, '让健康生活离家更近', 1008, 1390, 18, MUTED, 400, 'right');
  return canvas.toDataURL('image/png');
}
