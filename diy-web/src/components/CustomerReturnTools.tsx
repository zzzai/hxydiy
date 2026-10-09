import { useEffect, useRef, useState } from 'react';
import { Bookmark, CalendarDays, ChevronRight, MessageSquareText, X } from 'lucide-react';
import { QRCodeCanvas } from 'qrcode.react';
import { MEMBERSHIP_STORE_CONFIRMATION } from '../profile';
import { returnBannerKey, safeStoreContact, stableStoreEntry, STORE_CONTACTS } from '../returnEntry';

type Panel = 'save' | 'contact' | null;

function StoreContactQr({ value, name }: { value: string; name: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [image, setImage] = useState('');
  useEffect(() => {
    const frame = requestAnimationFrame(() => { if (canvas.current) setImage(canvas.current.toDataURL('image/png')); });
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <><QRCodeCanvas ref={canvas} value={value} size={512} level="M" marginSize={4} style={{ display: 'none' }} />{image && <img className="store-contact-qr" src={image} alt={`${name}企微联系二维码`} />}</>;
}

function ReturnDialog({ panel, storeId, onClose }: { panel: Panel; storeId: number; onClose: () => void }) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const closeButton = useRef<HTMLButtonElement>(null);
  const contact = safeStoreContact(STORE_CONTACTS[storeId]);
  const url = stableStoreEntry(window.location.origin, storeId);
  useEffect(() => {
    setCopyState('idle');
    if (!panel) return;
    const previous = document.activeElement as HTMLElement | null;
    closeButton.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.stopPropagation(); onClose(); }
      if (event.key === 'Tab') {
        const items = [...(closeButton.current?.closest('section')?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input') || [])];
        const target = event.shiftKey ? items.at(-1) : items[0];
        if (event.shiftKey && document.activeElement === items[0] || !event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); target?.focus(); }
      }
    };
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('keydown', escape); previous?.focus(); };
  }, [panel, onClose]);
  if (!panel) return null;
  return <div className="return-dialog-backdrop" onClick={onClose}>
    <section className="return-dialog" role="dialog" aria-modal="true" aria-label={panel === 'save' ? '保存门店入口' : '联系门店'} onClick={event => event.stopPropagation()}>
      <header><h2>{panel === 'save' ? '下次不用找沙发码' : '联系门店'}</h2><button ref={closeButton} type="button" aria-label="关闭入口提示" onClick={onClose}><X size={20} /></button></header>
      {panel === 'save' ? <>
        <p>保存门店入口，随时回来查看本人报告。到店选项目时，再扫描服务位二维码。</p>
        <label className="return-link-field">门店固定入口<input readOnly value={url} onFocus={event => event.currentTarget.select()} aria-label="门店固定入口" /></label>
        <button className="return-primary" type="button" onClick={async () => {
          try { await navigator.clipboard.writeText(url); setCopyState('copied'); }
          catch { setCopyState('failed'); }
        }}>复制门店入口</button>
        <p role="status" className="return-copy-status">{copyState === 'copied' ? '链接已复制，可粘贴给自己保存。' : copyState === 'failed' ? '无法自动复制，请长按上方链接手动复制。' : '微信中可先打开此入口，再点右上角「…」收藏。'}</p>
        <small>复制不等于已收藏；在新浏览器打开，可能需要重新登录。</small>
      </> : <>
        <h3>{contact?.name || '荷小悦门店联系'}</h3>
        {contact ? <>
          {contact.qrImage && <img className="store-contact-qr" src={contact.qrImage} alt={`${contact.name}官方企微联系我二维码`} />}
          {!contact.qrImage && contact.addUrl && <StoreContactQr value={contact.addUrl} name={contact.name} />}
          {contact.addUrl && <a className="return-primary" href={contact.addUrl} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">添加门店企微</a>}
          <p>可保存二维码，使用微信扫一扫，自愿添加门店。</p>
          <p>打开入口不代表已添加成功，请按企微页面提示操作。</p>
        </> : <p className="store-contact-unconfigured" role="status">门店线上联系方式尚未配置，到店可联系前台。</p>}
        <small>自愿添加，不影响查看本人报告和正常服务。</small>
      </>}
    </section>
  </div>;
}

export function ReturnEntryBanner({ storeId }: { storeId: number }) {
  const [closed, setClosed] = useState(() => { try { return localStorage.getItem(returnBannerKey(storeId)) === '1'; } catch { return false; } });
  const [panel, setPanel] = useState<Panel>(null);
  if (closed) return null;
  return <>
    <aside className="return-entry-banner" aria-label="保存门店入口提示"><Bookmark size={19} aria-hidden="true" /><strong>下次也能找到荷小悦</strong><div><button type="button" onClick={() => setPanel('save')}>保存入口</button><button type="button" onClick={() => setPanel('contact')}>联系门店</button></div><button className="return-banner-close" type="button" aria-label="关闭保存入口提示" onClick={() => { setClosed(true); try { localStorage.setItem(returnBannerKey(storeId), '1'); } catch { /* Keep dismissal in memory when storage is unavailable. */ } }}><X size={17} /></button></aside>
    <ReturnDialog panel={panel} storeId={storeId} onClose={() => setPanel(null)} />
  </>;
}

export function ProfileReturnTools({ storeId }: { storeId: number }) {
  const [panel, setPanel] = useState<Panel>(null);
  const contact = safeStoreContact(STORE_CONTACTS[storeId]);
  return <section className="profile-return-tools" aria-label="门店回访入口">
    <div className="profile-return-card return-save-card"><Bookmark size={23} aria-hidden="true" /><div><h3>下次不用找沙发码</h3><p>保存门店入口，随时回来。</p></div><button type="button" onClick={() => setPanel('save')}>保存入口</button></div>
    <div className="profile-return-card return-contact-card"><MessageSquareText size={23} aria-hidden="true" /><div><small>门店联系</small><h3>{contact?.name || '荷小悦门店联系'}</h3><p>{contact ? '自愿添加，不影响报告和服务。' : '线上联系方式尚未配置'}</p></div><button type="button" onClick={() => setPanel('contact')}>{contact ? '查看联系' : '查看说明'}<ChevronRight size={14} /></button></div>
    <details className="profile-tuesday-card"><summary><CalendarDays size={21} aria-hidden="true" /><div><h3>超级星期二</h3><p>有效会员按门店价消费主项，买一赠一。</p></div><span>查看活动</span></summary><div><p>每周二，有效会员按门店价消费任意主项，买一赠一。</p><p>适用主项、赠送搭配、补差和叠加规则，请到店由门店人工确认。</p><p>{MEMBERSHIP_STORE_CONFIRMATION}</p></div></details>
    <ReturnDialog panel={panel} storeId={storeId} onClose={() => setPanel(null)} />
  </section>;
}
