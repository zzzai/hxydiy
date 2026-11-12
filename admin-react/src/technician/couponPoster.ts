import QRCode from 'qrcode';

const POSTER_WIDTH = 1080;
const POSTER_HEIGHT = 1440;
const MASCOT_URL = '/assets/hxy-mascot.webp';

function escapeXml(value: string) {
  const entities: Record<string, string> = { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;' };
  return value.replace(/[<>&"']/g, (char) => entities[char] || char);
}

async function toDataUrl(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) throw new Error('海报素材加载失败');
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('海报素材加载失败'));
    reader.readAsDataURL(blob);
  });
}

function svgText(x: number, y: number, text: string, size: number, color: string, weight = 400, anchor = 'start') {
  return `<text x="${x}" y="${y}" fill="${color}" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" font-family="PingFang SC, Microsoft YaHei, Noto Sans SC, sans-serif">${escapeXml(text)}</text>`;
}

export async function createCouponPoster(link: string, storeName: string): Promise<Blob> {
  const [mascot, qr] = await Promise.all([
    toDataUrl(MASCOT_URL),
    QRCode.toDataURL(link, {
      width: 640,
      margin: 2,
      errorCorrectionLevel: 'M',
      color: { dark: '#145545', light: '#FFFFFF' },
    }),
  ]);
  const store = storeName.replace(/^荷小悦[-·]?/, '').replace(/^草本泡脚[（(]?/, '').replace(/[）)]$/, '') || '本店';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${POSTER_WIDTH}" height="${POSTER_HEIGHT}" viewBox="0 0 ${POSTER_WIDTH} ${POSTER_HEIGHT}">
    <rect width="1080" height="1440" fill="#F7F2E6"/>
    <ellipse cx="120" cy="20" rx="360" ry="300" fill="#1F8F75" opacity=".08"/>
    <ellipse cx="1010" cy="120" rx="250" ry="280" fill="#C69B3C" opacity=".10"/>
    <ellipse cx="880" cy="1080" rx="260" ry="180" fill="#1F8F75" opacity=".05"/>

    <circle cx="104" cy="96" r="32" fill="#145545"/>
    <text x="104" y="108" text-anchor="middle" fill="#FFFFFF" font-size="30" font-weight="700" font-family="PingFang SC, Microsoft YaHei, sans-serif">荷</text>
    ${svgText(156, 92, '荷小悦', 30, '#145545', 700)}
    ${svgText(158, 122, '草本轻养 · 半价券', 18, '#647A71')}

    ${svgText(72, 278, '忙完一天，', 72, '#132A24', 700)}
    ${svgText(72, 374, '来泡个脚，', 72, '#132A24', 700)}
    ${svgText(72, 470, '给自己松一松。', 72, '#132A24', 700)}
    ${svgText(76, 526, '草本现煮 · 到店即享', 28, '#A86D23', 600)}

    <circle cx="830" cy="330" r="178" fill="#FFFBEE" stroke="#C69B3C" stroke-width="5"/>
    ${svgText(830, 280, '全单', 26, '#A86D23', 600, 'middle')}
    ${svgText(830, 378, '5折', 112, '#145545', 700, 'middle')}
    ${svgText(830, 432, '60 天有效', 22, '#647A71', 400, 'middle')}

    <image href="${mascot}" x="70" y="600" width="500" height="500" preserveAspectRatio="xMidYMid meet"/>
    <path d="M585 650 C620 620 654 628 664 656" fill="none" stroke="#1F8F75" stroke-width="3" stroke-linecap="round" opacity=".8"/>
    <path d="M610 720 C640 700 670 706 680 730" fill="none" stroke="#1F8F75" stroke-width="3" stroke-linecap="round" opacity=".6"/>
    <path d="M548 1060 C578 1040 610 1046 620 1070" fill="none" stroke="#1F8F75" stroke-width="3" stroke-linecap="round" opacity=".55"/>

    <rect x="650" y="620" width="350" height="430" rx="26" fill="#FFFFFF" stroke="#E2C98F" stroke-width="2"/>
    <image href="${qr}" x="685" y="660" width="280" height="280" preserveAspectRatio="xMidYMid meet"/>
    ${svgText(825, 990, '扫码领取', 27, '#145545', 700, 'middle')}
    ${svgText(825, 1024, '到店出示核销码', 17, '#647A71', 400, 'middle')}

    <rect x="56" y="1120" width="968" height="254" rx="34" fill="#145545"/>
    ${svgText(92, 1214, '全单 5 折', 86, '#FFFFFF', 700)}
    ${svgText(96, 1270, `草本泡脚 · 到店即享 · ${store}`, 23, '#D9ECDF')}
    ${svgText(96, 1312, '扫码领取 · 登录后自动存入券包', 20, '#F3DFAA')}
    <circle cx="938" cy="1238" r="48" fill="none" stroke="#C69B3C" stroke-width="2"/>
    <text x="938" y="1252" text-anchor="middle" fill="#F3DFAA" font-size="36" font-weight="700" font-family="PingFang SC, Microsoft YaHei, sans-serif">荷</text>
  </svg>`;

  const svgUrl = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }));
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error('海报生成失败'));
      image.src = svgUrl;
    });
    const canvas = document.createElement('canvas');
    canvas.width = POSTER_WIDTH;
    canvas.height = POSTER_HEIGHT;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('海报生成失败');
    context.drawImage(image, 0, 0, POSTER_WIDTH, POSTER_HEIGHT);
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('海报生成失败')), 'image/png');
    });
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}
