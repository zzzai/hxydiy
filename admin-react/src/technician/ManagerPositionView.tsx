import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Drawer, Spin, Typography } from 'antd';
import { getLiveServicePositionMap, getStaff } from '../api';
import { selectionChangeItemSummary } from '../selectionChanges';
import { isMobileManager, managerError } from './managerMobile';
import { groupManagerPositionCards, positionDetailMatches, projectManagerPositions } from './managerPositions';
import type { ManagerPositionCard, ManagerPositionDetail, ManagerPositionMap } from './managerPositions';
import { useTechnicianSession } from './useTechnicianSession';

type DetailKey = Pick<ManagerPositionDetail, 'positionId' | 'occupancyId' | 'selectionId'>;
const groups = [{ type: 'sofa', name: '沙发' }, { type: 'bed', name: '床位' }, { type: 'room', name: '房间' }] as const;
export default function ManagerPositionView({ storeId, refreshKey }: { storeId: number; refreshKey: number }) {
  const current = useTechnicianSession();
  const [map, setMap] = useState<ManagerPositionMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [identity, setIdentity] = useState<DetailKey | null>(null);
  const [changed, setChanged] = useState(false);
  const version = useRef(0);
  const pending = useRef<number | null>(null);
  const pageActive = useRef(true);
  const detailRef = useRef(identity);
  detailRef.current = identity;
  const allowed = useCallback(() => current() && pageActive.current && isMobileManager(getStaff()) && getStaff()?.store_id === storeId, [current, storeId]);
  const load = useCallback(async (force = false) => {
    if (!allowed() || (!force && pending.current !== null)) return;
    const request = ++version.current;
    pending.current = request;
    setLoading(true);
    try {
      const response = await getLiveServicePositionMap();
      if (!allowed() || request !== version.current) return;
      const next = projectManagerPositions(response.data, storeId);
      const key = detailRef.current;
      if (key && !positionDetailMatches(next.positions.find(item => item.id === key.positionId), key)) setChanged(true);
      setMap(next); setError('');
    } catch (failure) {
      if (!allowed() || request !== version.current) return;
      setMap(null); setError(managerError(failure).text);
    } finally {
      if (pending.current === request) pending.current = null;
      if (allowed() && request === version.current) setLoading(false);
    }
  }, [allowed, storeId]);
  useEffect(() => {
    void load(true);
    return () => { ++version.current; pending.current = null; };
  }, [load, refreshKey]);
  useEffect(() => {
    const invalidate = () => {
      ++version.current; pending.current = null;
      setMap(null); setIdentity(null); setChanged(false); setError(''); setLoading(true);
    };
    const hide = () => { pageActive.current = false; invalidate(); };
    const show = () => { pageActive.current = true; void load(true); };
    const visibility = () => { if (document.visibilityState !== 'visible') hide(); else show(); };
    const refresh = () => { if (document.visibilityState === 'visible') void load(); };
    const timer = window.setInterval(refresh, 3000);
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', show);
    window.addEventListener('focus', refresh); document.addEventListener('visibilitychange', visibility);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', show);
      window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', visibility);
    };
  }, [load]);
  const visibleMap = allowed() && map?.storeId === storeId ? map : null;
  const cards = groupManagerPositionCards(visibleMap?.positions || []);
  const activeCard = identity ? cards.find(item => item.id === identity.positionId) : undefined;
  const detail = identity && !changed && positionDetailMatches(activeCard, identity) ? activeCard?.detail : undefined;
  const close = () => { setIdentity(null); setChanged(false); };
  const renderCard = (card: ManagerPositionCard) => <article className="manager-position-card" key={card.id}>
    <div className="manager-position-card-heading"><h3>{card.name}</h3>{!card.enabled && <span>已停用</span>}</div>
    <p className={'manager-position-state is-' + card.association}>{card.statusLabel}</p>
    {card.detail && <><ul className="manager-item-list">{card.detail.items.length ? card.detail.items.map((item, i) => <li key={i}>{selectionChangeItemSummary(item)}</li>) : <li>未填写项目</li>}</ul>
      <div className="manager-position-card-footer"><strong>{card.detail.price.value}</strong><Button onClick={() => {
        setIdentity({ positionId: card.id, occupancyId: card.detail!.occupancyId, selectionId: card.detail!.selectionId }); setChanged(false);
      }} aria-label={'查看' + card.name + '详情'}>查看详情</Button></div></>}
    {card.association === 'unverified' && <p className="manager-position-note">暂不展示选单，请刷新核对</p>}
  </article>;
  const disabled = cards.filter(card => !card.enabled);
  return <section className="manager-position-view" aria-label="门店座位">
    {error && <Alert type="error" showIcon message="座位加载失败" description={error} action={<Button onClick={() => void load(true)}>重试</Button>} />}
    {loading && !visibleMap && !error && <div className="manager-empty"><Spin size="small" /><span>正在加载座位</span></div>}
    {!error && visibleMap && !cards.length && <div className="manager-empty"><strong>尚未配置服务位</strong></div>}
    {groups.map(group => {
      const members = cards.filter(card => card.enabled && card.type === group.type);
      return members.length > 0 && <section className="manager-position-group" key={group.type} aria-label={group.name}>
        <h2>{group.name}<span>{members.length}</span></h2><div className="manager-position-grid">{members.map(renderCard)}</div>
      </section>;
    })}
    {disabled.length > 0 && <details className="manager-position-disabled" open={disabled.some(card => card.association !== 'none') || undefined}>
      <summary>已停用服务位 · {disabled.length}{disabled.some(card => card.association !== 'none') ? ' · 仍有关联需核对' : ''}</summary>
      <div className="manager-position-grid">{disabled.map(renderCard)}</div>
    </details>}
    <Drawer title={activeCard?.name || '座位详情'} placement="bottom" height="min(90dvh, 760px)" rootClassName="manager-detail-drawer" open={Boolean(identity) && allowed()} onClose={close} destroyOnClose footer={<div className="manager-detail-actions"><Button size="large" onClick={close}>关闭详情</Button><Button size="large" loading={loading} onClick={() => void load(true)}>刷新座位</Button></div>}>
      {error ? <Alert type="error" message="座位加载失败，请重试" /> : changed || (visibleMap && identity && !detail) ? <Alert type="warning" message="关联已变化" description="这个位置的当前选单已变化。请关闭详情，重新选择座位查看。" /> : !detail ? <Spin size="small" /> : <>
        <div className="manager-detail-intro"><strong>{activeCard?.statusLabel}</strong><span>只读</span></div>
        <div className="manager-change-identity"><Typography.Paragraph copyable={{ text: detail.selectionId }}>选单 · {detail.selectionId.slice(-8)}</Typography.Paragraph></div>
        <ul className="manager-item-list">{detail.items.length ? detail.items.map((item, i) => <li key={i}>{selectionChangeItemSummary(item)}</li>) : <li>未填写项目</li>}</ul>
        <div className="manager-detail-price"><span>{detail.price.label} <small>{detail.price.priceType}</small></span><strong>{detail.price.value}</strong></div>
        <dl className="manager-detail-meta"><div><dt>选单状态</dt><dd>{detail.selectionState}</dd></div><div><dt>来源</dt><dd>{detail.source}</dd></div></dl>
        <p className="manager-detail-note">确认、取消或安排座位，请到“选单”中处理。</p>
      </>}
    </Drawer>
  </section>;
}
