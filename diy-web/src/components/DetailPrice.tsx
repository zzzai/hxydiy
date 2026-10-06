import { formatMoney } from '../domain';

export default function DetailPrice({ current, comparison, isMember, unit, packagePrice, available = true, showMember = true }: {
  current: number; comparison: number; isMember: boolean; unit?: string; packagePrice?: boolean; available?: boolean; showMember?: boolean;
}) {
  if (!available) return <div className="mini-detail-price">价格待确认</div>;
  const samePrice = current === comparison;
  return <div className="mini-detail-price">
    <span className="detail-price-primary"><span className="detail-price-label">{packagePrice ? '套盒价' : !showMember ? '门店价' : samePrice ? '门店价 / 会员价' : isMember ? '会员价' : '门店价'}</span><strong>{formatMoney(current)}{packagePrice ? '/套' : ''}</strong></span>
    {!packagePrice && showMember && !samePrice && (isMember
      ? <del>门店价 {formatMoney(comparison)}</del>
      : <span className="member-reference-price">会员价 {formatMoney(comparison)}</span>)}
    {unit && <span className="detail-price-unit">{unit}</span>}
  </div>;
}
