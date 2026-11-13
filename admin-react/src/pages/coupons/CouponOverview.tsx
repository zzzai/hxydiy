import { useEffect, useState } from 'react';
import { Alert, Button, Card, Skeleton, Space, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getCouponOverview } from '../../api';
import { requestErrorMessage } from '../../requestError';

type Overview = {
  store_id: number;
  days: number;
  templates: { total: number; published: number; draft: number };
  coupons: { total: number; unused: number; locked: number; used: number; expired: number };
  posters: { total: number; claimed: number; unclaimed: number };
  period: { issued: number; redeemed_events: number; unique_customers: number };
  issuance_policy: { automatic_enabled: boolean; label: string };
};

type Props = { storeId?: number; refreshKey: number; onOpenTab?: (tab: string) => void };

export default function CouponOverview({ storeId, refreshKey, onOpenTab }: Props) {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    void getCouponOverview(storeId, 30)
      .then((response) => { if (active) setData(response.data); })
      .catch((failure) => { if (active) { setData(null); setError(requestErrorMessage(failure)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [storeId, refreshKey, attempt]);

  if (loading) return <Card><Skeleton active paragraph={{ rows: 5 }} /></Card>;
  if (error || !data) return <Card>
    <Alert type="error" showIcon message="券概览加载失败" description={error || '没有返回数据'} />
    <Button style={{ marginTop: 12 }} icon={<ReloadOutlined />} onClick={() => setAttempt(value => value + 1)}>重试</Button>
  </Card>;

  const cells = [
    { label: '券模板', value: data.templates.total, note: `${data.templates.published} 个已发布 · ${data.templates.draft} 个草稿`, tab: 'rules' },
    { label: '全部已发', value: data.coupons.total, note: '按实际创建的顾客券计数', tab: 'ledger' },
    { label: '当前可用', value: data.coupons.unused, note: '未使用、未过期、未锁定', tab: 'ledger' },
    { label: '已核销', value: data.coupons.used, note: '成功扫码核销的券', tab: 'redemptions' },
    { label: '已过期', value: data.coupons.expired, note: '按当前时间计算，不修改历史状态', tab: 'ledger' },
    { label: '锁定中', value: data.coupons.locked, note: '订单占用，不能重复使用', tab: 'ledger' },
  ];

  return <div className="coupon-overview">
    <div className="coupon-overview-top">
      <div>
        <p className="coupon-kicker">近 30 天</p>
        <h2>券运营概览</h2>
        <p className="coupon-muted">所有数字都可以追到券台账或核销记录；生成海报不等于发券。</p>
      </div>
      <Tag color={data.templates.published > 0 ? 'green' : 'default'}>{data.templates.published} 个模板生效</Tag>
    </div>

    <div className="coupon-stat-grid">
      {cells.map(cell => <Card key={cell.label} size="small" hoverable={Boolean(onOpenTab)} className="coupon-stat-card" onClick={() => onOpenTab?.(cell.tab)} role={onOpenTab ? 'button' : undefined} tabIndex={onOpenTab ? 0 : undefined}>
        <span>{cell.label}</span>
        <strong>{cell.value}</strong>
        <small>{cell.note}</small>
      </Card>)}
    </div>

    <div className="coupon-overview-columns">
      <Card size="small" title="近 30 天发放与核销">
        <div className="coupon-period-row" onClick={() => onOpenTab?.('ledger')}><span>新发 / 领取券</span><strong>{data.period.issued}</strong></div>
        <div className="coupon-period-row" onClick={() => onOpenTab?.('redemptions')}><span>成功核销事件</span><strong>{data.period.redeemed_events}</strong></div>
        <div className="coupon-period-row"><span>涉及顾客</span><strong>{data.period.unique_customers}</strong></div>
        <p className="coupon-footnote">核销事件独立按核销时间统计，包含以前领取、本期核销的券；不与本期发券强行算转化率。</p>
      </Card>
      <Card size="small" title="单券海报入口">
        <div className="coupon-period-row" onClick={() => onOpenTab?.('posters')}><span>生成海报</span><strong>{data.posters.total}</strong></div>
        <div className="coupon-period-row"><span>已被领取</span><strong>{data.posters.claimed}</strong></div>
        <div className="coupon-period-row"><span>仍可领取</span><strong>{data.posters.unclaimed}</strong></div>
        <p className="coupon-footnote">一张新海报对应一个领取入口；打开或生成海报不预扣券额度。</p>
      </Card>
    </div>

    <Alert type={data.issuance_policy.automatic_enabled ? 'success' : 'warning'} showIcon message={data.issuance_policy.label}
      description={data.issuance_policy.automatic_enabled ? '普通新客、主动领取、分享和邀请自动发券策略已启用；店长海报和手工发券仍按既有边界工作。' : '普通新客、主动领取、分享和邀请自动发券仍暂停；本页不会因为模板上架而自动发券，店长海报和手工发券按既有边界工作。'} />
    <Alert type="info" showIcon message="统计口径"
      description="“已发”包含未使用、锁定、已使用和已过期券；固定面额券预算按全部已发券占用，过期或核销不会释放预算。营业收入与优惠成本需要支付/订单关联，本页不展示推断值。" />
  </div>;
}
