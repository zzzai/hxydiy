import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Bookmark, CalendarDays, ChevronRight, Copy, MessageSquareText, Search, X } from 'lucide-react';
import { QRCodeCanvas } from 'qrcode.react';
import { MEMBERSHIP_STORE_CONFIRMATION } from '../profile';
import { returnBannerKey, safeStoreContact, STORE_CONTACTS } from '../returnEntry';

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
  return <div className={`return-dialog-backdrop ${panel === 'save' ? 'service-account-backdrop' : ''}`} onClick={onClose}>
    <section className={`return-dialog ${panel === 'save' ? 'service-account-sheet' : ''}`} role="dialog" aria-modal="true" aria-label={panel === 'save' ? '服务号入口' : '联系门店'} onClick={event => event.stopPropagation()}>
      {panel === 'save' && <img className="service-account-mascot" src="/assets/hxy-mascot.webp" alt="" />}
      <header><h2>{panel === 'save' ? '下次来，不用找沙发码' : contact ? '周二会员福利' : '联系门店'}</h2><button ref={closeButton} type="button" aria-label="关闭入口提示" onClick={onClose}><X size={20} /></button></header>
      {panel === 'save' ? <>
        <div className="service-account-body">
        <div className="service-account-identity"><img src="/assets/hxy-mascot.webp" alt="" /><div><h3>荷小悦草本轻养</h3><p>荷小悦服务号</p></div></div>
        <ol className="service-account-steps" aria-label="关注步骤"><li><span>1</span>长按识别<ArrowRight size={20} aria-hidden="true" /></li><li><span>2</span>关注服务号</li></ol>
        <img className="service-account-qr" src="/assets/hxy-service-account-qr.jpg" alt="荷小悦草本轻养服务号二维码，长按识别" />
        <h3 className="service-account-action">长按上方二维码，识别服务号</h3>
        <p className="service-account-next">下次从服务号底部菜单进入</p>
        <p className="service-account-features">选项目 · 查看本人报告</p>
        <div className="service-account-search"><Search size={18} aria-hidden="true" /><span>也可微信搜索：荷小悦草本轻养</span><button type="button" onClick={async () => {
          try { await navigator.clipboard.writeText('荷小悦草本轻养'); setCopyState('copied'); }
          catch { setCopyState('failed'); }
        }}><Copy size={16} aria-hidden="true" />复制名称</button></div>
        {copyState !== 'idle' && <p role="status" className="service-account-copy-status">{copyState === 'copied' ? '名称已复制，可到微信搜索。' : '无法自动复制，可在微信搜索「荷小悦草本轻养」。'}</p>}
        <small className="service-account-note">自愿关注，不影响正常服务。<br />报告需本人登录并授权查看。</small>
        </div>
      </> : <>
        <h3>{contact?.name || '荷小悦门店联系'}</h3>
        {contact ? <>
          <p>会员周二按门店价消费任意主项，买一赠一。</p>
          <small>添加店长企微，了解门店活动。</small>
          {contact.qrImage && <img className="store-contact-qr" src={contact.qrImage} alt={`${contact.name}官方企微联系我二维码`} />}
          {!contact.qrImage && contact.addUrl && <StoreContactQr value={contact.addUrl} name={contact.name} />}
          <p className="store-contact-instruction">长按二维码，添加店长企微</p>
        </> : <p className="store-contact-unconfigured" role="status">门店线上联系方式尚未配置，到店可联系前台。</p>}
        <small>{contact ? '自愿添加，不影响服务与报告查看。' : '自愿添加，不影响查看本人报告和正常服务。'}</small>
      </>}
    </section>
  </div>;
}

export function ReturnEntryBanner({ storeId }: { storeId: number }) {
  const [closed, setClosed] = useState(() => { try { return localStorage.getItem(returnBannerKey(storeId)) === '1'; } catch { return false; } });
  const [panel, setPanel] = useState<Panel>(null);
  if (closed) return null;
  return <>
    <aside className="return-entry-banner" aria-label="服务号入口提示"><Bookmark size={19} aria-hidden="true" /><strong>下次从服务号进入</strong><div><button type="button" onClick={() => setPanel('save')}>查看入口</button><button type="button" onClick={() => setPanel('contact')}>联系门店</button></div><button className="return-banner-close" type="button" aria-label="关闭服务号入口提示" onClick={() => { setClosed(true); try { localStorage.setItem(returnBannerKey(storeId), '1'); } catch { /* Keep dismissal in memory when storage is unavailable. */ } }}><X size={17} /></button></aside>
    <ReturnDialog panel={panel} storeId={storeId} onClose={() => setPanel(null)} />
  </>;
}

export function ProfileReturnTools({ storeId }: { storeId: number }) {
  const [panel, setPanel] = useState<Panel>(null);
  const contact = safeStoreContact(STORE_CONTACTS[storeId]);
  return <section className="profile-return-tools" aria-label="门店回访入口">
    <div className="profile-return-card return-save-card"><Bookmark size={23} aria-hidden="true" /><div><h3>下次从服务号进入</h3><p>荷小悦草本轻养 · 底部菜单</p></div><button type="button" onClick={() => setPanel('save')}>查看入口</button></div>
    <div className="profile-return-card return-contact-card"><MessageSquareText size={23} aria-hidden="true" /><div><small>门店联系</small><h3>{contact?.name || '荷小悦门店联系'}</h3><p>{contact ? '自愿添加，不影响报告和服务。' : '线上联系方式尚未配置'}</p></div><button type="button" onClick={() => setPanel('contact')}>{contact ? '查看联系' : '查看说明'}<ChevronRight size={14} /></button></div>
    <details className="profile-tuesday-card"><summary><CalendarDays size={21} aria-hidden="true" /><div><h3>超级星期二</h3><p>有效会员按门店价消费主项，买一赠一。</p></div><span>查看活动</span></summary><div><p>每周二，有效会员按门店价消费任意主项，买一赠一。</p><p>适用主项、赠送搭配、补差和叠加规则，请到店由门店人工确认。</p><p>{MEMBERSHIP_STORE_CONFIRMATION}</p></div></details>
    <ReturnDialog panel={panel} storeId={storeId} onClose={() => setPanel(null)} />
  </section>;
}
