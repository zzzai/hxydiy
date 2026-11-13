import { useEffect, useState } from 'react';
import { Button, Spin, Tag } from 'antd';
import { getManagerCouponHistory, type ManagerCouponHistoryItem, type ManagerCouponHistoryKind, type ManagerCouponHistorySummary } from '../api';
import './manager-coupon-history.css';
import { formatDateTime } from '../utils/couponFormat';

type Filter = 'all' | ManagerCouponHistoryKind;

const EMPTY_SUMMARY: ManagerCouponHistorySummary = { issued: 0, redeemed: 0, unused: 0, locked: 0, expired: 0 };

function timeText(value: string) {
  return formatDateTime(value);
}

function statusLabel(status: ManagerCouponHistoryItem['status']) {
  return status === 'used' ? '已核销' : status === 'expired' ? '已过期' : status === 'locked' ? '锁定中' : '待使用';
}

function kindLabel(kind: ManagerCouponHistoryKind) {
  return kind === 'redeemed' ? '核销记录' : '发券记录';
}

export default function ManagerCouponHistoryView({ embedded = false }: { embedded?: boolean } = {}) {
  const [days, setDays] = useState(30);
  const [filter, setFilter] = useState<Filter>('all');
  const [summary, setSummary] = useState<ManagerCouponHistorySummary>(EMPTY_SUMMARY);
  const [items, setItems] = useState<ManagerCouponHistoryItem[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<ManagerCouponHistoryItem | null>(null);

  const load = async (reset = true) => {
    const offset = reset ? 0 : nextOffset ?? 0;
    if (reset) { setLoading(true); setError(''); } else setLoadingMore(true);
    try {
      const response = await getManagerCouponHistory({ days, kind: filter, limit: 30, offset });
      setSummary(response.data.summary);
      setItems((current) => reset ? response.data.items : [...current, ...response.data.items]);
      setNextOffset(response.data.next_offset);
    } catch {
      setError('券记录加载失败，请重试');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => { void load(true); }, [days, filter]);

  return <section className="manager-coupon-history" aria-label="券记录">
    {!embedded ? <div className="manager-coupon-history-head">
      <div>
        <p>本店发券、领取与核销记录；生成链接不计入发券。</p>
      </div>
      <Button size="small" onClick={() => void load(true)}>刷新</Button>
    </div> : null}

    <div className="manager-coupon-history-summary">
      <div><strong>{summary.issued}</strong><span>发券</span></div>
      <div><strong>{summary.redeemed}</strong><span>核销</span></div>
      <div><strong>{summary.unused}</strong><span>待使用</span></div>
      <div><strong>{summary.locked}</strong><span>锁定中</span></div>
      <div className="expired"><strong>{summary.expired}</strong><span>已过期</span></div>
    </div>

    <div className="manager-coupon-history-toolbar">
      <div className="manager-coupon-history-filters" role="group" aria-label="券记录筛选">
        {([['all', '全部'], ['issued', '发券'], ['redeemed', '核销']] as const).map(([value, label]) => (
          <button type="button" key={value} className={filter === value ? 'active' : ''} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>
        ))}
      </div>
      <div className="manager-coupon-history-range" role="group" aria-label="时间范围">
        <button type="button" className={days === 30 ? 'active' : ''} aria-pressed={days === 30} onClick={() => setDays(30)}>近30天</button>
        <button type="button" className={days === 7 ? 'active' : ''} aria-pressed={days === 7} onClick={() => setDays(7)}>近7天</button>
      </div>
    </div>

    {loading ? <div className="manager-coupon-history-loading"><Spin size="small" /> 正在加载券记录…</div> : null}
    {!loading && error ? <div className="manager-coupon-history-error"><p>{error}</p><Button size="small" onClick={() => void load(true)}>重试</Button></div> : null}
    {!loading && !error && !items.length ? <div className="manager-coupon-history-empty">
      <strong>近 {days} 天还没有券记录</strong>
      <p>店长发出或顾客领取后，会在这里留下记录。</p>
    </div> : null}

    {!loading && !error && items.length > 0 ? <div className="manager-coupon-history-list">
      {items.map((item) => <button type="button" key={item.id} className={`manager-coupon-history-row ${item.kind}`} onClick={() => setSelected(item)}>
        <span className="manager-coupon-history-icon" aria-hidden="true">{item.kind === 'redeemed' ? '核' : item.source === 'direct' ? '发' : '领'}</span>
        <span className="manager-coupon-history-copy">
          <strong>{item.kind === 'redeemed' ? `${item.customer_name}核销半价券` : item.source === 'direct' ? `店长给${item.customer_name}发券` : `${item.customer_name}领取半价券`}</strong>
          <small>{item.kind === 'redeemed' ? `店长 ${item.actor_name || '—'} · 本店核销` : item.source === 'direct' ? '店长直接发券' : '微信链接领取'}{item.phone_masked && item.phone_masked !== '—' ? ` · ${item.phone_masked}` : ''}</small>
        </span>
        <span className="manager-coupon-history-side">
          <Tag color={item.status === 'used' ? 'green' : item.status === 'expired' ? 'default' : 'gold'}>{statusLabel(item.status)}</Tag>
          <time dateTime={item.at}>{timeText(item.at)}</time>
        </span>
      </button>)}
    </div> : null}

    {nextOffset !== null && !loading ? <button type="button" className="manager-coupon-history-more" disabled={loadingMore} onClick={() => void load(false)}>{loadingMore ? '加载中…' : '加载更多'}</button> : null}

    {selected ? <div className="manager-coupon-history-backdrop" role="presentation" onClick={() => setSelected(null)}>
      <section className="manager-coupon-history-sheet" role="dialog" aria-modal="true" aria-labelledby="coupon-history-detail-title" onClick={(event) => event.stopPropagation()}>
        <div className="manager-coupon-history-grab" />
        <p className="manager-coupon-history-kicker">{kindLabel(selected.kind)}</p>
        <h3 id="coupon-history-detail-title">{selected.kind === 'redeemed' ? `${selected.customer_name}核销半价券` : selected.source === 'direct' ? `店长给${selected.customer_name}发券` : `${selected.customer_name}领取半价券`}</h3>
        <p className="manager-coupon-history-sub">{selected.template_name} · {selected.source === 'direct' ? '店长直接发券' : '微信链接领取'}</p>
        <div className={`manager-coupon-history-status ${selected.status}`}><i />{statusLabel(selected.status)}</div>
        <dl>
          <div><dt>时间</dt><dd>{timeText(selected.at)}</dd></div>
          <div><dt>顾客</dt><dd>{selected.customer_name}{selected.phone_masked && selected.phone_masked !== '—' ? ` · ${selected.phone_masked}` : ''}</dd></div>
          {selected.kind === 'redeemed' ? <div><dt>核销人</dt><dd>店长 {selected.actor_name || '—'}</dd></div> : null}
        </dl>
        <Button block onClick={() => setSelected(null)}>关闭</Button>
      </section>
    </div> : null}
  </section>;
}
