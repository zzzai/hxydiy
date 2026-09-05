import { formatMoney } from '../domain';

export default function DetailPrice({ current, comparison, isMember, unit }: {
  current: number; comparison: number; isMember: boolean; unit?: string;
}) {
  const samePrice = current === comparison;
  return <div className="mini-detail-price">
    <span className="detail-price-primary"><span className="detail-price-label">{samePrice ? '门店价 / 会员价' : isMember ? '会员价' : '门店价'}</span><strong>{formatMoney(current)}</strong></span>
    {!samePrice && (isMember
      ? <del>门店价 {formatMoney(comparison)}</del>
      : <span className="member-reference-price">会员价 {formatMoney(comparison)}</span>)}
    {unit && <span className="detail-price-unit">{unit}</span>}
  </div>;
}
