import QRCode from 'qrcode';

const WIDTH = 1080;
const HEIGHT = 1440;
const MASCOT_URL = '/assets/hxy-mascot.webp';

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

function text(context: CanvasRenderingContext2D, value: string, x: number, y: number, size: number, color: string, weight = 400, align: CanvasTextAlign = 'left') {
  context.font = `${weight} ${size}px "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif`;
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

  context.fillStyle = '#F7F2E6';
  context.fillRect(0, 0, WIDTH, HEIGHT);

  context.save();
  context.globalAlpha = 0.08;
  context.fillStyle = '#1F8F75';
  context.beginPath();
  context.ellipse(120, 20, 360, 300, 0, 0, Math.PI * 2);
  context.fill();
  context.globalAlpha = 0.1;
  context.fillStyle = '#C69B3C';
  context.beginPath();
  context.ellipse(1010, 120, 250, 280, 0, 0, Math.PI * 2);
  context.fill();
  context.globalAlpha = 0.05;
  context.fillStyle = '#1F8F75';
  context.beginPath();
  context.ellipse(880, 1080, 260, 180, 0, 0, Math.PI * 2);
  context.fill();
  context.restore();

  context.fillStyle = '#145545';
  context.beginPath();
  context.arc(104, 96, 32, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = '#FFFFFF';
  context.font = '700 30px "PingFang SC", "Microsoft YaHei", sans-serif';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText('荷', 104, 98);
  text(context, '荷小悦', 156, 68, 30, '#145545', 700);
  text(context, '草本轻养 · 半价券', 158, 108, 18, '#647A71');

  text(context, '忙完一天，', 72, 210, 72, '#132A24', 700);
  text(context, '来泡个脚，', 72, 306, 72, '#132A24', 700);
  text(context, '给自己松一松。', 72, 402, 72, '#132A24', 700);
  text(context, '草本现煮 · 到店即享', 76, 500, 28, '#A86D23', 600);

  context.fillStyle = '#FFFBEE';
  context.strokeStyle = '#C69B3C';
  context.lineWidth = 5;
  context.beginPath();
  context.arc(830, 330, 178, 0, Math.PI * 2);
  context.fill();
  context.stroke();
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillStyle = '#A86D23';
  context.font = '600 26px "PingFang SC", "Microsoft YaHei", sans-serif';
  context.fillText('全单', 830, 270);
  context.fillStyle = '#145545';
  context.font = '700 112px "PingFang SC", "Microsoft YaHei", sans-serif';
  context.fillText('5折', 830, 354);
  context.fillStyle = '#647A71';
  context.font = '400 22px "PingFang SC", "Microsoft YaHei", sans-serif';
  context.fillText('60 天有效', 830, 434);

  context.drawImage(mascot, 70, 600, 500, 500);

  context.strokeStyle = 'rgba(31, 143, 117, .7)';
  context.lineWidth = 3;
  context.lineCap = 'round';
  for (const [x, y, rx, ry, start, end] of [[585, 650, 80, 34, 3.5, 5.9], [610, 720, 70, 30, 3.5, 5.8], [548, 1060, 72, 30, 3.5, 5.8]] as const) {
    context.beginPath();
    context.ellipse(x, y, rx, ry, 0, start, end);
    context.stroke();
  }

  roundedRect(context, 650, 620, 350, 430, 26);
  context.fillStyle = '#FFFFFF';
  context.fill();
  context.strokeStyle = '#E2C98F';
  context.lineWidth = 2;
  context.stroke();
  context.drawImage(qr, 685, 660, 280, 280);
  context.textAlign = 'center';
  context.textBaseline = 'top';
  context.fillStyle = '#145545';
  context.font = '700 27px "PingFang SC", "Microsoft YaHei", sans-serif';
  context.fillText('扫码领取', 825, 960);
  context.fillStyle = '#647A71';
  context.font = '400 17px "PingFang SC", "Microsoft YaHei", sans-serif';
  context.fillText('到店出示核销码', 825, 1000);

  roundedRect(context, 56, 1120, 968, 254, 34);
  context.fillStyle = '#145545';
  context.fill();
  text(context, '全单 5 折', 92, 1160, 86, '#FFFFFF', 700);
  text(context, `草本泡脚 · 到店即享 · ${store}`, 96, 1262, 23, '#D9ECDF');
  text(context, '扫码领取 · 登录后自动存入券包', 96, 1302, 20, '#F3DFAA');
  context.strokeStyle = '#C69B3C';
  context.lineWidth = 2;
  context.beginPath();
  context.arc(938, 1238, 48, 0, Math.PI * 2);
  context.stroke();
  context.fillStyle = '#F3DFAA';
  context.font = '700 36px "PingFang SC", "Microsoft YaHei", sans-serif';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText('荷', 938, 1240);

  return canvas.toDataURL('image/png');
}
