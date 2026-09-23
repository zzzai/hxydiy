export type ServicePositionQrAction = 'enable' | 'disable' | 'regenerate' | 'rebind';

export type ServicePositionQrPermissions = {
  canView: boolean;
  canManage: boolean;
};

export const servicePositionQrRenderOptions = {
  width: 1024,
  margin: 4,
  errorCorrectionLevel: 'M' as const,
};

export type PrintablePositionQr = {
  code: string;
  name: string;
  image: string;
};

export function printablePositionQrs<T extends { id: number; type: string; operational_status: string }>(positions: T[]): T[] {
  return positions.filter((position) => position.id > 0
    && (position.type === 'sofa' || position.type === 'bed')
    && position.operational_status === 'active');
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character] || character);
}

export function buildPositionQrPrintDocument(items: PrintablePositionQr[]): string {
  const cards = items.map((item) => `<article><img src="${item.image}" alt="${escapeHtml(item.name)}顾客二维码" /><h1>${escapeHtml(item.name)}</h1><p>${escapeHtml(item.code)}</p></article>`).join('');
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>荷小悦服务位二维码</title><style>
    @page { size: A4; margin: 12mm; }
    body { font-family: system-ui, sans-serif; color: #173f34; }
    main { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10mm; }
    article { break-inside: avoid; text-align: center; border: 1px solid #d9e4df; padding: 7mm; border-radius: 4mm; }
    img { display: block; width: 72mm; height: 72mm; margin: 0 auto 4mm; }
    h1 { margin: 0; font-size: 16pt; } p { margin: 2mm 0 0; color: #587068; font-size: 10pt; }
  </style></head><body><main>${cards}</main></body></html>`;
}

export function getServicePositionQrPermissions(role?: string): ServicePositionQrPermissions {
  const canView = role === 'admin' || role === 'manager' || role === 'staff';
  return {
    canView,
    canManage: role === 'manager',
  };
}

export function servicePositionQrActions(status: string, replaced: boolean): ServicePositionQrAction[] {
  if (replaced) return [];
  return status === 'active'
    ? ['disable', 'regenerate', 'rebind']
    : ['enable', 'regenerate', 'rebind'];
}
