import { useState } from 'react';
import { Space, Tabs, Tag } from 'antd';
import { getStaff } from '../api';
import { hasCapability } from '../core/auth/capabilities';
import StoreScopeSelect from '../components/StoreScopeSelect';
import CouponOverview from './coupons/CouponOverview';
import CouponRulesPanel from './coupons/CouponRulesPanel';
import CouponPosterPanel from './coupons/CouponPosterPanel';
import CouponLedgerPanel from './coupons/CouponLedgerPanel';
import CouponRedemptionPanel from './coupons/CouponRedemptionPanel';
import './coupons/coupon-admin.css';

export default function CouponsPage() {
  const staff = getStaff();
  const [storeId, setStoreId] = useState<number>();
  const [tab, setTab] = useState('overview');
  const [refreshKey, setRefreshKey] = useState(0);
  const canManage = hasCapability(staff?.role, 'manage_marketing', staff?.store_id, staff?.technician_id);

  return <div className="coupon-admin-page">
    <div className="coupon-admin-header">
      <div>
        <p className="coupon-kicker">营销券 · 运营</p>
        <h1>券运营</h1>
        <p>从规则、海报入口、顾客券台账追到核销事件；每个汇总数字都有明细口径。</p>
      </div>
      <Space wrap>
        <StoreScopeSelect value={storeId} onChange={(value) => { setStoreId(value); setRefreshKey(key => key + 1); }} />
        <Tag color={canManage ? 'green' : 'default'}>{canManage ? '规则可维护' : '仅可查看本店记录'}</Tag>
      </Space>
    </div>

    <Tabs activeKey={tab} onChange={setTab} items={[
      { key: 'overview', label: '概览', children: <CouponOverview storeId={storeId} refreshKey={refreshKey} onOpenTab={setTab} /> },
      { key: 'rules', label: '券规则', children: <CouponRulesPanel storeId={storeId} canManage={canManage} /> },
      { key: 'posters', label: '海报记录', children: <CouponPosterPanel storeId={storeId} /> },
      { key: 'ledger', label: '券台账', children: <CouponLedgerPanel storeId={storeId} /> },
      { key: 'redemptions', label: '核销记录', children: <CouponRedemptionPanel storeId={storeId} /> },
    ]} />
  </div>;
}
