import { formatMoney } from '../domain';

export default function DetailPrice({ current, comparison, isMember, unit }: {
  current: number; comparison: number; isMember: boolean; unit?: string;
}) {
  const samePrice = current === comparison;
  return <div className="mini-detail-price">
    <strong>{formatMoney(current)}</strong>
    {!samePrice && (isMember
      ? <del>门店价 {formatMoney(comparison)}</del>
      : <span className="member-reference-price">会员价 {formatMoney(comparison)}</span>)}
    <em>{samePrice ? '门店价 / 会员价' : isMember ? '会员价' : '门店价'}{unit && ` · ${unit}`}</em>
  </div>;
}
