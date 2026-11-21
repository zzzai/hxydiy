import { ChevronRight, Leaf, Store, UserRound, Wallet } from 'lucide-react';
import { useId, useState } from 'react';

import type { CustomerMembershipOverview } from '../api';
import type { CustomerUser } from '../customerAuth';
import { formatMemberCents } from '../domain';
import { ANNUAL_MEMBERSHIP_BENEFITS, formatDateTime, membershipState, STORED_MEMBERSHIP_TEA } from '../profile';
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
  if (card.balance.reconciliation === 'zero_balance_against_active_card_review') return '余额为零';
  return card.status === 'active' ? (card.usable ? '当前可用' : '当前不可用') : card.status === 'disabled' ? '已停用' : card.status === 'expired' ? '已到期' : card.status === 'exhausted' ? '余额用尽' : card.status === 'scheduled' ? '未开始' : '用卡前请咨询门店';
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
  const verifiedIdentity = membership.data?.identity;
  const identity = verifiedIdentity ?? user;
  const memberType = card?.card_type ?? (identity.is_member ? identity.member_type : null);
  const kind = card && !card.usable ? 'inactive' : memberType ?? 'guest';
  const stored = memberType === 'stored';
  const memberLabel = stored ? '储值会员' : memberType === 'annual' ? '年卡会员' : identity.is_member ? '会员' : '荷小悦顾客';
  const expiry = card ? card.expires_at : identity.is_member ? identity.member_expire_at : null;
  const state = membershipState(expiry);
  const validTerm = state.kind === 'active' || state.kind === 'expiring';
  const showPlan = verifiedIdentity?.is_member && (
    (memberType === 'annual' && validTerm) || (stored && (!expiry || validTerm))
  );
  const comparison = consumption.data?.store_price_comparison;
  const priceComparison = comparison?.basis === 'historical_store_price_minus_settlement';
  const savings = priceComparison ? comparison : consumption.data?.savings;
  const savingsCents = savings?.status === 'verified' ? savings.amount_cents : null;
  const balanceCents = stored && card && balanceKnown(card) ? card.balance.amount_cents : null;
  const balanceDate = date(card?.balance.observed_at);
  const totalBills = consumption.data?.pagination.total;
  return <>
    <section className="profile-member-overview" data-kind={kind ?? 'guest'} aria-label="会员概览">
      <div className="profile-overview-identity">
        <span className="profile-overview-avatar" aria-hidden="true"><UserRound size={24} /></span>
        <div className="profile-overview-name"><h1>{user.nickname || '荷小悦顾客'}</h1><p>{phoneLabel(user.phone)}</p></div>
        <span className="profile-overview-badge">{stored ? <Wallet size={14} aria-hidden="true" /> : <Leaf size={14} aria-hidden="true" />}{memberLabel}</span>
      </div>
      {card && <p className="profile-overview-store"><Store size={14} aria-hidden="true" />{card.store_name || `门店 #${card.store_id}`}{(!card.usable || card.balance.reconciliation === 'zero_balance_against_active_card_review') && <span> · {cardStatus(card)}</span>}</p>}
      {cards.length > 1 && <label className="profile-overview-card-picker">我的会员卡<select aria-label="切换会员卡" value={card?.id} onChange={event => setSelectedId(Number(event.target.value))}>{cards.map((item, index) => <option key={item.id} value={item.id}>{item.card_type_label} · {item.store_name || `门店 #${item.store_id}`} · 第{index + 1}张（{cardStatus(item)}）</option>)}</select></label>}
      {expiry && <p className="profile-overview-expiry">{state.kind === 'expired' ? '权益已到期' : '权益有效期至'} {date(expiry)}{state.kind === 'expiring' && ` · 还有${state.daysLeft}天`}</p>}
      {(balanceCents !== null || savingsCents !== null) && <div className="profile-overview-metrics">
        {balanceCents !== null && <button type="button" className="profile-overview-metric" aria-controls={benefitsId} aria-expanded={benefitsOpen} onClick={() => setBenefitsOpen(value => !value)}>
          <span>储值余额<ChevronRight size={12} aria-hidden="true" /></span><strong>{formatMemberCents(balanceCents)}</strong>
          {balanceDate && <small>{balanceDate}更新</small>}
        </button>}
        {savingsCents !== null && <button type="button" className="profile-overview-metric profile-consumption-savings" aria-controls={historyId} aria-expanded={historyOpen} onClick={() => setHistoryOpen(value => !value)}>
          <span>{priceComparison ? '较门店价已省' : '累计消费优惠'}<ChevronRight size={12} aria-hidden="true" /></span><strong>{formatMemberCents(savingsCents)}</strong>
          {savings?.bill_count != null && <small>已核实{savings.bill_count}笔消费</small>}
        </button>}
      </div>}
      <details className="profile-overview-disclosure" id={benefitsId} open={benefitsOpen} onToggle={event => setBenefitsOpen(event.currentTarget.open)}>
        <summary><span>会员权益</span><DisclosureEnd open={benefitsOpen} /></summary>
        <div className="profile-overview-benefits">
          {membership.loading ? <p role="status">正在加载会员信息…</p> : membership.error ? <><p role="alert">会员信息暂时无法加载，请重试。</p><button type="button" className="profile-overview-retry" onClick={membership.retry}>重新加载会员信息</button></> : card ? <>
            <p className="profile-overview-card-state">{card.card_type_label} · {cardStatus(card)}</p>
            {card.started_at && <p className="profile-overview-small">开卡日期 {date(card.started_at)}{!expiry && ' · 有效期以门店记录为准'}</p>}
            {card.usable && <><ul>{card.benefits.map(benefit => <li key={benefit}>{benefit}</li>)}</ul><p>{card.benefits_note}</p></>}
            {!card.usable && <p>这张卡目前无法使用，其他有效会员卡不受影响。</p>}
            {stored && <div className="profile-overview-balance-note">
              {balanceCents === null ? <p>余额请向办卡门店查询。</p> : <>
                <p>{card.balance.reconciliation === 'zero_balance_against_active_card_review' ? '用卡前请联系办卡门店。' : '到店可用余额以门店最新记录为准。'}</p>
                {card.balance.split === 'verified' && card.balance.principal_cents !== null && card.balance.bonus_cents !== null && <p>本金 {formatMemberCents(card.balance.principal_cents)} · 赠金 {formatMemberCents(card.balance.bonus_cents)}</p>}
                <p>这是本店储值卡余额，与在线钱包分开。</p>
              </>}
            </div>}
          </> : showPlan ? <>
            <p className="profile-overview-card-state">{stored ? '储值卡标准权益' : '年卡标准权益'}</p>
            <ul>
              <li>{ANNUAL_MEMBERSHIP_BENEFITS.standard}</li>
              <li>{ANNUAL_MEMBERSHIP_BENEFITS.tuesday}</li>
              <li>{ANNUAL_MEMBERSHIP_BENEFITS.gift}</li>
              {stored && <li>{STORED_MEMBERSHIP_TEA}</li>}
            </ul>
            {stored && <p>余额请向办卡门店查询。</p>}
            <p>权益在适用门店使用。周二活动的搭配、补差和叠加由门店确认，开卡赠礼的领取情况以门店记录为准。</p>
          </> : <p>{identity.is_member ? '具体权益请向门店查询。' : '暂未关联有效会员卡，如已在门店办卡，请联系办卡门店。'}</p>}
        </div>
      </details>
      {showMemberCode && identity.is_member && state.kind !== 'expired' && <button type="button" className="profile-member-code-button" onClick={onShowCode}>出示动态会员码</button>}
    </section>
    <details className="profile-consumption profile-overview-disclosure" id={historyId} open={historyOpen} onToggle={event => setHistoryOpen(event.currentTarget.open)}>
      <summary><span>消费记录</span><DisclosureEnd open={historyOpen} label={totalBills ? `${totalBills}笔` : undefined} /></summary>
      <ConsumptionDetails consumption={consumption} multipleCards={cards.length > 1} showCalculation={savingsCents !== null} />
    </details>
  </>;
}

function ConsumptionDetails({ consumption, multipleCards, showCalculation }: {
  consumption: Props['consumption']; multipleCards: boolean; showCalculation: boolean;
}) {
  const { data, bills, loading, error, hasMore, loadingMore, retry, loadMore } = consumption;
  if (loading) return <p className="profile-overview-message" role="status">正在加载消费记录…</p>;
  if (error && !bills.length) return <div className="profile-overview-message"><p role="alert">消费记录暂时无法加载，请重试。</p><button type="button" className="profile-overview-retry" onClick={retry}>重新加载消费记录</button></div>;
  if (!data || !bills.length) return <p className="profile-overview-message">这里暂无门店消费记录。</p>;

  const comparison = data.store_price_comparison;
  const priceComparison = comparison?.basis === 'historical_store_price_minus_settlement';
  const { query_range_start, query_range_end, complete } = data.coverage;
  return <div className="profile-overview-history-content">
    {showCalculation && <details className="profile-overview-calculation">
      <summary>金额怎么算<ChevronRight size={14} aria-hidden="true" /></summary>
      <p>{priceComparison ? <>每笔按当次门店价减去结算金额计算。结算金额包含储值卡、券等支付方式。已省金额不含退款调整。{comparison.unverified_bill_count > 0 && `另有${comparison.unverified_bill_count}笔消费未计入。`}</> : '仅合计门店账单中有明确金额的优惠。'}{multipleCards && '多张会员卡的消费合并计算。'}</p>
    </details>}
    <ul className="profile-consumption-bills">{bills.map(bill => {
      const savings = priceComparison ? bill.price_comparison : bill.savings;
      const saved = savings?.status === 'verified' ? savings.amount_cents : null;
      const title = bill.lines[0]?.description || '门店消费';
      const billInfo = [date(bill.occurred_at), data.coverage.store_ids.length > 1 && `门店 #${bill.store_id}`].filter(Boolean).join(' · ');
      const prices = [
        bill.store_price_total_cents !== null && `门店价 ${formatMemberCents(bill.store_price_total_cents, bill.currency)}`,
        bill.settled_total_cents !== null && `结算 ${formatMemberCents(bill.settled_total_cents, bill.currency)}`,
      ].filter(Boolean).join(' · ');
      return <li key={bill.id} className="profile-consumption-bill">
        <div className="profile-overview-bill-heading">
          <div><strong>{title}{bill.lines.length > 1 && `等${bill.lines.length}项`}</strong>{billInfo && <small>{billInfo}</small>}</div>
          {(bill.settled_total_cents !== null || saved !== null) && <div>
            {bill.settled_total_cents !== null && <strong>{formatMemberCents(bill.settled_total_cents, bill.currency)}</strong>}
            {saved !== null && <small>{priceComparison ? '较门店价省' : '优惠'} {formatMemberCents(saved, bill.currency)}</small>}
          </div>}
        </div>
        <details><summary>查看明细<ChevronRight size={12} aria-hidden="true" /></summary>
          {prices && <p>{prices}</p>}
          <ul>{bill.lines.map((line, i) => <li key={i}>{line.description}{line.quantity !== null ? ` × ${line.quantity}` : ''}{line.settled_cents !== null ? ` · ${formatMemberCents(line.settled_cents, bill.currency)}` : ''}</li>)}</ul>
          <p>账单：{bill.source_bill_no}</p>
        </details>
      </li>;
    })}</ul>
    {hasMore && <button type="button" className="profile-consumption-more" onClick={loadMore} disabled={loadingMore}>{loadingMore ? '加载中…' : '加载更多'}</button>}
    {error && bills.length > 0 && <p className="profile-overview-message" role="alert">后续记录加载失败，请重试。</p>}
    {(query_range_start && query_range_end || complete === false) && <p className="profile-consumption-scope">
      {query_range_start && query_range_end && `记录时段 ${date(query_range_start)} 至 ${date(query_range_end)}。`}
      {complete === false && '仅显示部分门店消费记录。'}
    </p>}
  </div>;
}
