import { ChevronRight, Leaf, Store, UserRound, Wallet } from 'lucide-react';
import { useId, useState } from 'react';

import type { CustomerMembershipOverview } from '../api';
import type { CustomerUser } from '../customerAuth';
import { formatMemberCents } from '../domain';
import { formatDateTime, membershipState } from '../profile';
import type { useCustomerMembership } from './useCustomerMembership';
import type { useCustomerConsumption } from './useCustomerConsumption';
import './profile-member-overview.css';

type Card = CustomerMembershipOverview['cards'][number];
type Props = {
  user: CustomerUser;
  membership: ReturnType<typeof useCustomerMembership>;
  consumption: ReturnType<typeof useCustomerConsumption>;
  showMemberCode: boolean;
  onShowCode: () => void;
};

function cardStatus(card: Card) {
  if (card.balance.reconciliation === 'zero_balance_against_active_card_review') return '状态待门店核实';
  return card.status === 'active' ? (card.usable ? '当前可用' : '当前不可用') : card.status === 'disabled' ? '已停用' : card.status === 'expired' ? '已到期' : card.status === 'exhausted' ? '余额用尽' : card.status === 'scheduled' ? '未开始' : '待核实';
}

function balanceKnown(card: Card) {
  return ['observed', 'source_snapshot'].includes(card.balance.status) && card.balance.amount_cents !== null;
}

function date(value: string | null | undefined) {
  return value ? formatDateTime(value).slice(0, 10) : '';
}

function phoneLabel(phone: string) {
  const normalized = phone.replace(/\D/g, '');
  return normalized.length === 11 ? `${normalized.slice(0, 3)}****${normalized.slice(-4)}` : '手机号已绑定';
}

function DisclosureEnd({ open, label }: { open: boolean; label?: string }) {
  return <span className="profile-overview-disclosure-end">{label ?? (open ? '收起' : '查看')}<ChevronRight size={16} aria-hidden="true" /></span>;
}

export default function ProfileMemberOverview({ user, membership, consumption, showMemberCode, onShowCode }: Props) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [benefitsOpen, setBenefitsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const benefitsId = useId();
  const historyId = useId();
  const cards = membership.data?.cards ?? [];
  // Prefer a usable stored card, but preserve each card's own balance and status.
  const preferredCard = cards.find(card => card.usable && card.card_type === 'stored') ?? cards.find(card => card.usable) ?? cards[0];
  const card = cards.find(item => item.id === selectedId) ?? preferredCard;
  const kind = card ? (card.usable ? card.card_type : 'inactive') : user.is_member ? user.member_type : 'guest';
  const stored = card?.card_type === 'stored' || (!card && user.is_member && user.member_type === 'stored');
  const memberLabel = card ? (card.card_type === 'stored' ? '储值会员' : '年卡会员') : user.is_member ? (user.member_type === 'stored' ? '储值会员' : user.member_type === 'annual' ? '年卡会员' : '会员') : '荷小悦顾客';
  const expiry = card?.expires_at ?? (!card ? user.member_expire_at : null);
  const state = membershipState(expiry);
  const comparison = consumption.data?.store_price_comparison;
  const priceComparison = comparison?.basis === 'historical_store_price_minus_settlement';
  const savings = priceComparison ? comparison : consumption.data?.savings;
  const verifiedSavings = savings?.status === 'verified' && savings.amount_cents !== null;
  const hasRecords = (consumption.data?.pagination.total ?? consumption.bills.length) > 0;
  const savingsValue = consumption.loading ? '加载中…' : consumption.error && !consumption.data ? '暂不可用' : verifiedSavings ? formatMemberCents(savings!.amount_cents!) : hasRecords ? '待核实' : '暂无记录';
  const savingsNote = verifiedSavings && savings?.bill_count != null ? `已核实${savings.bill_count}笔消费` : consumption.loading ? '正在加载消费记录' : consumption.error && !consumption.data ? '点击重试' : hasRecords ? '核实后再展示' : '同步后展示';
  const balanceValue = membership.loading ? '加载中…' : membership.error ? '暂不可用' : card && balanceKnown(card) ? formatMemberCents(card.balance.amount_cents!) : '待核实';
  const balanceDate = date(card?.balance.observed_at);
  const savingsTitle = priceComparison || !consumption.data ? '较门店价已省' : '累计消费优惠';
  return <>
    <section className="profile-member-overview" data-kind={kind ?? 'guest'} aria-label="会员概览">
      <div className="profile-overview-identity">
        <span className="profile-overview-avatar" aria-hidden="true"><UserRound size={24} /></span>
        <div className="profile-overview-name"><h1>{user.nickname || '荷小悦顾客'}</h1><p>{phoneLabel(user.phone)}</p></div>
        <span className="profile-overview-badge">{stored ? <Wallet size={14} aria-hidden="true" /> : <Leaf size={14} aria-hidden="true" />}{memberLabel}</span>
      </div>
      {card && <p className="profile-overview-store"><Store size={14} aria-hidden="true" />{card.store_name || `门店 #${card.store_id}`}{(!card.usable || cardStatus(card) === '状态待门店核实') && <span> · {cardStatus(card)}</span>}</p>}
      {cards.length > 1 && <label className="profile-overview-card-picker">我的会员卡<select aria-label="切换会员卡" value={card?.id} onChange={event => setSelectedId(Number(event.target.value))}>{cards.map((item, index) => <option key={item.id} value={item.id}>{item.card_type_label} · {item.store_name || `门店 #${item.store_id}`} · 第{index + 1}张（{cardStatus(item)}）</option>)}</select></label>}
      {expiry && <p className="profile-overview-expiry">{state.kind === 'expired' ? '权益已到期' : '权益有效期至'} {date(expiry)}{state.kind === 'expiring' && ` · 还有${state.daysLeft}天`}</p>}
      <div className={`profile-overview-metrics ${stored ? 'has-balance' : ''}`}>
        {stored && <button type="button" className="profile-overview-metric" aria-controls={benefitsId} aria-expanded={benefitsOpen} onClick={() => setBenefitsOpen(value => !value)}><span>储值余额<ChevronRight size={12} aria-hidden="true" /></span><strong className={balanceValue.startsWith('¥') ? '' : 'is-message'}>{balanceValue}</strong><small>{membership.error ? '点击查看并重试' : balanceDate ? `${balanceDate}更新` : '暂未确认更新时间'}</small></button>}
        <button type="button" className="profile-overview-metric profile-consumption-savings" aria-controls={historyId} aria-expanded={historyOpen} onClick={() => setHistoryOpen(value => !value)}><span>{savingsTitle}<ChevronRight size={12} aria-hidden="true" /></span><strong className={savingsValue.startsWith('¥') ? '' : 'is-message'}>{savingsValue}</strong><small>{savingsNote}</small></button>
      </div>
      <details className="profile-overview-disclosure" id={benefitsId} open={benefitsOpen} onToggle={event => setBenefitsOpen(event.currentTarget.open)}>
        <summary><span>会员权益</span><DisclosureEnd open={benefitsOpen} /></summary>
        <div className="profile-overview-benefits">
          {membership.loading ? <p role="status">正在加载会员信息…</p> : membership.error ? <><p role="alert">会员信息暂时无法加载，请重试。</p><button type="button" className="profile-overview-retry" onClick={membership.retry}>重新加载会员信息</button></> : card ? <>
            <p className="profile-overview-card-state">{card.card_type_label} · {cardStatus(card)}</p>
            {card.started_at && <p className="profile-overview-small">开卡日期 {date(card.started_at)}{!expiry && ' · 有效期以门店记录为准'}</p>}
            {card.usable && <><ul>{card.benefits.map(benefit => <li key={benefit}>{benefit}</li>)}</ul><p>{card.benefits_note}</p></>}
            {!card.usable && <p>这张卡目前无法使用，其他有效会员卡不受影响。</p>}
            {stored && <div className="profile-overview-balance-note">
              {card.balance.reconciliation === 'zero_balance_against_active_card_review' ? <p>余额为 0，状态待门店核实。</p> : !balanceKnown(card) ? <p>余额暂时无法确认，请联系门店核实。</p> : <p>余额并非实时金额{balanceDate ? `，最近更新于${balanceDate}` : ''}。</p>}
              {card.balance.split === 'verified' && card.balance.principal_cents !== null && card.balance.bonus_cents !== null ? <p>本金 {formatMemberCents(card.balance.principal_cents)} · 赠金 {formatMemberCents(card.balance.bonus_cents)}</p> : <p>余额包含的本金和赠金，请向门店查询。</p>}
              <p>这是本店储值卡余额，与在线钱包分开。</p>
            </div>}
          </> : <p>{user.is_member ? '会员身份已关联，具体权益请向门店查询。' : '暂未关联会员卡，如已在门店办卡，请联系门店核实。'}</p>}
        </div>
      </details>
      {showMemberCode && user.is_member && state.kind !== 'expired' && <button type="button" className="profile-member-code-button" onClick={onShowCode}>出示动态会员码</button>}
    </section>
    <details className="profile-consumption profile-overview-disclosure" id={historyId} open={historyOpen} onToggle={event => setHistoryOpen(event.currentTarget.open)}>
      <summary><span>消费记录</span><DisclosureEnd open={historyOpen} label={consumption.data ? (hasRecords ? `${consumption.data.pagination.total}笔` : '暂无记录') : consumption.loading ? '加载中…' : undefined} /></summary>
      <ConsumptionDetails consumption={consumption} multipleCards={cards.length > 1} />
    </details>
  </>;
}

function ConsumptionDetails({ consumption, multipleCards }: { consumption: Props['consumption']; multipleCards: boolean }) {
  const { data, bills, loading, error, hasMore, loadingMore, retry, loadMore } = consumption;
  if (loading) return <p className="profile-overview-message" role="status">正在加载消费记录…</p>;
  if (error && !bills.length) return <div className="profile-overview-message"><p role="alert">消费记录暂时无法加载，请重试。</p><button type="button" className="profile-overview-retry" onClick={retry}>重新加载消费记录</button></div>;
  if (!data) return <p className="profile-overview-message">暂未同步到您的消费记录。</p>;
  const comparison = data.store_price_comparison;
  const priceComparison = comparison?.basis === 'historical_store_price_minus_settlement';
  const range = data.coverage.query_range_start && data.coverage.query_range_end ? `${date(data.coverage.query_range_start)} ~ ${date(data.coverage.query_range_end)}` : '未记录';
  const coverageLabel = data.coverage.complete === true ? '已同步该时段记录' : data.coverage.complete === false ? (data.coverage.coverage_gaps ? '部分消费记录尚未同步' : '尚未完整同步') : '记录完整性待核实';
  return <div className="profile-overview-history-content">
    {!!comparison?.unverified_bill_count && <p className="profile-overview-small">{comparison.unverified_bill_count}笔金额待核实，暂未计入已省金额。</p>}
    <details className="profile-overview-calculation"><summary>金额怎么算<ChevronRight size={14} aria-hidden="true" /></summary>{priceComparison ? <p>按当次门店价与结算金额计算，不含退款调整。结算金额包含储值、券等支付，不等于现金支付；仅统计已核实的本人消费，不代表退款后的净节省。{multipleCards && '已省金额按本人已同步消费统计，不按所选会员卡分摊。'}</p> : <p>{data.savings.note}</p>}</details>
    {!bills.length ? <p className="profile-overview-message">暂未同步到可展示的消费记录{data.coverage.conflict_bill_groups > 0 ? `（${data.coverage.conflict_bill_groups}组记录待核实）` : ''}。</p> : <ul className="profile-consumption-bills">{bills.map(bill => {
      const savings = priceComparison ? bill.price_comparison : bill.savings;
      const title = bill.lines[0]?.description || '门店消费';
      return <li key={bill.id} className="profile-consumption-bill">
        <div className="profile-overview-bill-heading"><div><strong>{title}{bill.lines.length > 1 && `等${bill.lines.length}项`}</strong><small>{date(bill.occurred_at) || '消费时间未记录'}{data.coverage.store_ids.length > 1 && ` · 门店 #${bill.store_id}`}</small></div><div><strong>{bill.settled_total_cents !== null ? formatMemberCents(bill.settled_total_cents, bill.currency) : '金额待核实'}</strong><small>{savings?.status === 'verified' && savings.amount_cents !== null ? `${priceComparison ? '较门店价省' : '优惠'} ${formatMemberCents(savings.amount_cents, bill.currency)}` : '优惠金额待核实'}</small></div></div>
        <details><summary>查看明细<ChevronRight size={12} aria-hidden="true" /></summary><p>{bill.store_price_total_cents !== null ? `门店价 ${formatMemberCents(bill.store_price_total_cents, bill.currency)} · ` : ''}{bill.settled_total_cents !== null ? `结算 ${formatMemberCents(bill.settled_total_cents, bill.currency)}` : '结算金额待核实'}</p><ul>{bill.lines.map((line, i) => <li key={i}>{line.description}{line.quantity !== null ? ` × ${line.quantity}` : ''}{line.settled_cents !== null ? ` · ${formatMemberCents(line.settled_cents, bill.currency)}` : ''}</li>)}</ul><p>账单：{bill.source_bill_no}</p></details>
      </li>;
    })}</ul>}
    {hasMore && <button type="button" className="profile-consumption-more" onClick={loadMore} disabled={loadingMore}>{loadingMore ? '加载中…' : '加载更多'}</button>}
    {error && bills.length > 0 && <p className="profile-overview-message" role="alert">后续记录加载失败，请重试。</p>}
    <p className="profile-consumption-scope">记录时段：{range}；{coverageLabel}。金额待核实的消费不计入已省金额{data.coverage.observed_at ? `，最近更新于${date(data.coverage.observed_at)}` : ''}。</p>
  </div>;
}
