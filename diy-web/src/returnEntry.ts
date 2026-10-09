export type StoreContact = { name: string; qrImage?: string; addUrl?: string };

// Only verified official contact-me assets belong here; never login or personal QR codes.
export const STORE_CONTACTS: Readonly<Record<number, StoreContact>> = {
  1: { name: '紫薇壹号店 · 马文静', addUrl: 'https://work.weixin.qq.com/u/vcd649012bd26ad232?v=5.0.10.79677&bb=fcec4c6148' },
};

export function stableStoreEntry(origin: string, storeId: number): string {
  const url = new URL('/', origin);
  url.searchParams.set('store', String(Number.isSafeInteger(storeId) && storeId > 0 ? storeId : 1));
  url.searchParams.set('view', 'return');
  return url.href;
}

export function isReturnEntry(params: URLSearchParams): boolean {
  return params.get('view') === 'return' || (!params.get('seat') && !params.get('qr') && !params.get('session') && !params.get('project') && params.get('view') !== 'menu' && params.get('source') !== 'kiosk');
}

export function returnBannerKey(storeId: number): string {
  return `hxy_diy_return_notice_closed_${storeId}`;
}

export function safeStoreContact(contact?: StoreContact): StoreContact | null {
  if (!contact) return null;
  const qrImage = contact.qrImage && /^\/assets\/store-contact\/[A-Za-z0-9_-]+\.(png|webp|jpg)$/.test(contact.qrImage) ? contact.qrImage : undefined;
  let addUrl: string | undefined;
  if (contact.addUrl && /^https:\/\/work\.weixin\.qq\.com\//.test(contact.addUrl)) {
    try {
      const url = new URL(contact.addUrl);
      const params = [...url.searchParams];
      if (!url.hash && (/^\/ca\/[A-Za-z0-9_-]+$/.test(url.pathname) && !url.search || /^\/u\/[A-Za-z0-9_-]+$/.test(url.pathname) && params.length === 2 && /^\d+(\.\d+){1,5}$/.test(url.searchParams.get('v') || '') && /^[a-f0-9]{1,64}$/.test(url.searchParams.get('bb') || ''))) addUrl = contact.addUrl;
    } catch { /* Invalid contact links remain unconfigured. */ }
  }
  return qrImage || addUrl ? { name: contact.name, qrImage, addUrl } : null;
}
