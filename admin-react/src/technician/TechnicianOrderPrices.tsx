import { technicianOrderPriceView, technicianPriceLabel, type TechnicianOrderPricing } from './technicianMobile';

type PriceItem = { name?: unknown; quantity?: unknown; code?: unknown; diy_preferences?: unknown };

export default function TechnicianOrderPrices({
  pricing,
  items,
}: {
  pricing?: TechnicianOrderPricing | null;
  items?: PriceItem[] | null;
}) {
  const view = technicianOrderPriceView(pricing, items);
  if (!view) return null;
  return <div className="technician-service-prices">
    {view.rows.length > 0 && <ul>
      {view.rows.map((row, index) => <li key={`${row.name}-${index}`}>
        <span>{row.name}{row.quantity > 1 ? ` ×${row.quantity}` : ''}</span>
        <span>会员 {technicianPriceLabel(row.memberCents)} · 非会员 {technicianPriceLabel(row.storeCents)}</span>
      </li>)}
    </ul>}
    <section className="technician-order-pricing" aria-label="订单价格">
      <div className="technician-order-pricing-head">
        <span>本单价格</span>
        <span>{view.appliedLabel}</span>
      </div>
      <div className="technician-order-pricing-pair">
        <div><span>会员价合计</span><strong>{technicianPriceLabel(view.memberTotalCents)}</strong></div>
        <div><span>非会员价合计</span><strong>{technicianPriceLabel(view.storeTotalCents)}</strong></div>
      </div>
    </section>
  </div>;
}
