type WeChatShareData = ShareData & { imageUrl?: string };

type WeChatSdk = {
  config: (config: Record<string, unknown>) => void;
  ready: (callback: () => void) => void;
  error: (callback: () => void) => void;
  showOptionMenu: () => void;
  updateAppMessageShareData: (data: Record<string, unknown>) => void;
  updateTimelineShareData: (data: Record<string, unknown>) => void;
};

declare global {
  interface Window {
    wx?: WeChatSdk;
  }
}

const WECHAT_SDK_URL = 'https://res.wx.qq.com/open/js/jweixin-1.6.0.js';
let sdkLoading: Promise<WeChatSdk> | undefined;
let sdkReady: Promise<WeChatSdk> | undefined;

export function isWeChatBrowser(userAgent = navigator.userAgent): boolean {
  return /MicroMessenger/i.test(userAgent);
}

function loadWeChatSdk(): Promise<WeChatSdk> {
  if (window.wx) return Promise.resolve(window.wx);
  if (sdkLoading) return sdkLoading;
  sdkLoading = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = WECHAT_SDK_URL;
    script.async = true;
    script.onload = () => window.wx ? resolve(window.wx) : reject(new Error('WeChat SDK unavailable'));
    script.onerror = () => reject(new Error('WeChat SDK failed to load'));
    document.head.appendChild(script);
  });
  return sdkLoading;
}

async function ensureWeChatSdkReady(): Promise<WeChatSdk> {
  if (sdkReady) return sdkReady;
  sdkReady = (async () => {
    const sdk = await loadWeChatSdk();
    const signedUrl = window.location.href.split('#', 1)[0];
    const response = await fetch(`/api/v1/wechat/jssdk-config?url=${encodeURIComponent(signedUrl)}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('WeChat signing unavailable');
    const config = await response.json() as { appId: string; timestamp: number; nonceStr: string; signature: string };
    await new Promise<void>((resolve, reject) => {
      sdk.error(() => reject(new Error('WeChat SDK configuration failed')));
      sdk.ready(resolve);
      sdk.config({
        ...config,
        debug: false,
        jsApiList: ['showOptionMenu', 'updateAppMessageShareData', 'updateTimelineShareData'],
      });
    });
    return sdk;
  })().catch((error) => {
    sdkReady = undefined;
    throw error;
  });
  return sdkReady;
}

function sharePayload(data: WeChatShareData): Record<string, unknown> {
  return {
    title: data.title,
    desc: data.text,
    link: data.url,
    imgUrl: new URL(data.imageUrl || '/assets/hxy-mascot.webp', window.location.origin).toString(),
  };
}

export async function configureWeChatProjectShare(data: WeChatShareData): Promise<boolean> {
  if (!isWeChatBrowser()) return false;
  try {
    const sdk = await ensureWeChatSdkReady();
    const payload = sharePayload(data);
    sdk.showOptionMenu();
    sdk.updateAppMessageShareData(payload);
    sdk.updateTimelineShareData(payload);
    return true;
  } catch {
    return false;
  }
}
