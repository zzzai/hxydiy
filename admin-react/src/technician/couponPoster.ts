import QRCode from 'qrcode';

const WIDTH = 1080;
const HEIGHT = 1440;
const MASCOT_URL = '/assets/ip-paopao-running-bucket.webp';

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
  const source = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('海报素材加载失败'));
    reader.readAsDataURL(blob);
  });
  const image = await loadImage(source);
  const canvas = document.createElement('canvas');
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('海报素材加载失败');
  context.drawImage(image, 0, 0);
  return canvas.toDataURL('image/png');
}

function roundedRect(context: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  const r = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + r, y);
  context.arcTo(x + width, y, x + width, y + height, r);
  context.arcTo(x + width, y + height, x, y + height, r);
  context.arcTo(x, y + height, x, y, r);
  context.arcTo(x, y, x + width, y, r);
  context.closePath();
}

function text(context: CanvasRenderingContext2D, value: string, x: number, y: number, size: number, color: string, weight = 400, align: CanvasTextAlign = 'left', family = '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif') {
  context.font = `${weight} ${size}px ${family}`;
  context.fillStyle = color;
  context.textAlign = align;
  context.textBaseline = 'top';
  context.fillText(value, x, y);
}

export async function createCouponPoster(link: string, storeName: string): Promise<string> {
  const [mascotUrl, qrUrl] = await Promise.all([
    imageToPngDataUrl(MASCOT_URL),
    QRCode.toDataURL(link, {
      width: 640,
      margin: 2,
      errorCorrectionLevel: 'M',
      color: { dark: '#145545', light: '#FFFFFF' },
    }),
  ]);
  const [mascot, qr] = await Promise.all([loadImage(mascotUrl), loadImage(qrUrl)]);
  const store = escapeStoreName(storeName);

  const canvas = document.createElement('canvas');
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('海报生成失败');

  context.fillStyle = '#FBF8F0';
  context.fillRect(0, 0, WIDTH, HEIGHT);

  context.save();
  context.globalAlpha = 0.08;
  context.fillStyle = '#1F8F75';
  context.beginPath();
  context.ellipse(100, 20, 360, 280, 0, 0, Math.PI * 2);
  context.fill();
  context.globalAlpha = 0.08;
  context.fillStyle = '#C69B3C';
  context.beginPath();
  context.ellipse(1000, 100, 240, 250, 0, 0, Math.PI * 2);
  context.fill();
  context.restore();

  text(context, '荷小悦', 72, 62, 58, '#145545', 700);
  text(context, '草本泡脚', 74, 138, 28, '#145545');
  text(context, '®', 300, 70, 16, '#145545');

  roundedRect(context, 820, 72, 188, 54, 27);
  context.fillStyle = '#FFFFFF';
  context.fill();
  context.strokeStyle = '#E2C98F';
  context.lineWidth = 1;
  context.stroke();
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillStyle = '#A86D23';
  context.font = '700 18px "PingFang SC", "Microsoft YaHei", sans-serif';
  context.fillText('半价券 · 60天', 914, 100);

  const kai = '"Kaiti SC", "STKaiti", "KaiTi", "PingFang SC", serif';
  text(context, '累了，', 72, 292, 64, '#132A24', 400, 'left', kai);
  text(context, '就来荷小悦', 72, 372, 64, '#132A24', 400, 'left', kai);
  context.strokeStyle = '#A86D23';
  context.lineWidth = 3;
  context.beginPath();
  context.ellipse(197, 470, 122, 19, 0, 3.35, 6.05);
  context.stroke();
  text(context, '草本现煮 · 温暖放松', 76, 505, 24, '#A86D23', 600);

  text(context, '一桶草本热水，', 72, 620, 25, '#647A71');
  text(context, '把今天的疲惫泡掉。', 72, 660, 25, '#647A71');

  context.drawImage(mascot, 520, 220, 500, 592);

  context.strokeStyle = 'rgba(31, 143, 117, .7)';
  context.lineWidth = 3;
  context.lineCap = 'round';
  for (const [x, y, rx, ry, start, end] of [[470, 470, 60, 30, 3.5, 5.8], [470, 530, 48, 24, 3.5, 5.8], [960, 900, 44, 22, 3.5, 5.8]] as const) {
    context.beginPath();
    context.ellipse(x, y, rx, ry, 0, start, end);
    context.stroke();
  }

  text(context, '全场 5 折', 72, 980, 86, '#145545', 700);
  text(context, '小项除外', 78, 1088, 22, '#647A71');
  text(context, '60 天有效 · 扫码领取', 78, 1124, 20, '#A86D23');

  roundedRect(context, 640, 960, 340, 330, 24);
  context.fillStyle = '#FFFFFF';
  context.fill();
  context.strokeStyle = '#E2C98F';
  context.lineWidth = 2;
  context.stroke();
  context.drawImage(qr, 692, 988, 236, 236);
  context.textAlign = 'center';
  context.textBaseline = 'top';
  context.fillStyle = '#145545';
  context.font = '700 22px "PingFang SC", "Microsoft YaHei", sans-serif';
  context.fillText('扫码领取', 810, 1238);

  context.strokeStyle = '#E1DCCD';
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(72, 1340);
  context.lineTo(1008, 1340);
  context.stroke();
  text(context, `荷小悦 · ${store} · 家门口的养生小馆`, 72, 1358, 18, '#145545');
  text(context, '让健康生活离家更近', 74, 1396, 16, '#647A71');
  text(context, 'HXY', 942, 1358, 16, '#C69B3C', 700);

  return canvas.toDataURL('image/png');
}
