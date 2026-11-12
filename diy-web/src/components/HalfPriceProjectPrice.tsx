import { formatMoney, type Project } from '../domain';
import { halfPriceForProject } from '../halfPriceCoupon';

export default function HalfPriceProjectPrice({ project }: { project: Project }) {
  const cents = halfPriceForProject(project, true);
  if (cents === null) return null;
  const store = project.prices.find(price => price.price_type === 'store')?.amount_cents;
  return <div className="half-price-project">
    <div><small>持券价</small><strong>{formatMoney(cents)}</strong>{store != null && <del>门店价 {formatMoney(store)}</del>}</div>
    <span>主项5折 · 到店扫码核销</span>
  </div>;
}
