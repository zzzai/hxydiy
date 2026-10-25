import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Empty, Spin, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import { getTechnicianMyTasks } from '../api';
import type { TechnicianCustomerTask } from '../technicianCustomer';
import { technicianOrderItemLabel, technicianPriceLabel, technicianPriceMode, technicianPriceModeLabel, technicianPriceTotalValue, technicianPricedItemRows, technicianStatusLabel } from './technicianMobile';
import TechnicianCustomerPanel from './TechnicianCustomerPanel';
import TechnicianProfileSheet from './TechnicianProfileSheet';
import { useTechnicianSession } from './useTechnicianSession';
import './technician-customer.css';

export default function TechnicianMyServicesPage() {
  const navigate = useNavigate();
  const current = useTechnicianSession();
  const [tasks, setTasks] = useState<TechnicianCustomerTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [customer, setCustomer] = useState<number>();
  const [recordTask, setRecordTask] = useState<any>();
  const loadingRef = useRef(false);
  const closeCustomer = useCallback(() => setCustomer(undefined), []);
  const load = useCallback(async () => {
    if (loadingRef.current || !current()) return;
    loadingRef.current = true;
    try {
      const { data } = await getTechnicianMyTasks();
      if (!current()) return;
      setTasks(data.items); setError('');
      setCustomer((id) => data.items.some((item) => item.occupancy_id === id) ? id : undefined);
    } catch {
      if (current()) { setError('我的服务加载失败，请重试'); setCustomer(undefined); }
    } finally { loadingRef.current = false; if (current()) setLoading(false); }
  }, [current]);
  useEffect(() => {
    void load();
    const refresh = () => { if (document.visibilityState === 'visible') void load(); else closeCustomer(); };
    const timer = window.setInterval(refresh, 3000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, [load, closeCustomer]);
  return <section className="technician-my-services">
    <header><h1>我的服务</h1><p>查看本人正在服务和已结束的顾客；确认与结束操作在服务看板完成。</p></header>
    <Button block onClick={() => navigate('/positions')}>查看门店服务位</Button>
    {error && <Alert type="error" message={error} action={<Button onClick={() => void load()}>重试</Button>} />}
    {loading ? <Spin /> : tasks.length ? tasks.map((task) => {
      const pricing = task.pricing;
      const mode = technicianPriceMode(pricing);
      const modeLabel = technicianPriceModeLabel(mode);
      const total = technicianPriceTotalValue(mode, pricing);
      const rows = technicianPricedItemRows(task.items, pricing);
      const itemNames = task.items.map(technicianOrderItemLabel).filter(Boolean).join('、') || '未记录项目';
      return <article key={task.occupancy_id} className="technician-customer-entry">
        <h2>{task.room_name || '本次服务'} <Tag>{technicianStatusLabel(task.occupancy_status)}</Tag></h2>
        {pricing
          ? <div className="technician-my-service-items">
            {rows.length > 0 ? rows.map((row) => <div className="technician-my-service-item" key={row.key}>
              <span className="technician-my-service-item-name">{row.name}</span>
              <span className="technician-my-service-item-tail">
                {row.quantity > 1 && <span className="technician-my-service-item-count">×{row.quantity}</span>}
                {row.amount_cents != null && <span className="technician-my-service-item-price">{modeLabel} {technicianPriceLabel(row.amount_cents)}</span>}
                {row.amount_cents == null && row.pending_label && <span className="technician-my-service-item-pending">{row.pending_label}</span>}
              </span>
            </div>) : <p>未记录项目</p>}
          </div>
          : <p>{itemNames}</p>}
        {pricing && <section className="technician-order-pricing" aria-label="订单价格">
          <div className="technician-order-pricing-head"><span>本单价格</span><span>{modeLabel}</span></div>
          {mode !== 'unknown' && <div className="technician-order-pricing-pair">
            <div><span>{modeLabel}合计</span><strong>{total.pending_label ? '待确认' : technicianPriceLabel(total.amount_cents)}</strong></div>
          </div>}
          {mode === 'unknown' && <p className="technician-order-pricing-hint">价格类型待确认，暂不展示单价与合计</p>}
          {total.pending_label && <p className="technician-order-pricing-hint">{total.pending_label}</p>}
        </section>}
        <div className="technician-my-service-actions">
          <Button onClick={() => setCustomer(task.occupancy_id)}>顾客标签与资料</Button>
          {task.occupancy_status === 'post_service_present' && !task.record_completed && task.user_id && <Button type="primary" onClick={() => setRecordTask(task)}>填写服务记录</Button>}
          <Button disabled={!task.user_id} onClick={() => navigate('/history')}>查看服务记录</Button>
        </div>
        {!task.user_id && <p>匿名服务可正常完成，暂未关联顾客资料。</p>}
      </article>;
    }) : <Empty description="目前没有本人正在服务的顾客" />}
    {customer !== undefined && <TechnicianCustomerPanel key={customer} occupancyId={customer} onClose={closeCustomer} />}
    <TechnicianProfileSheet task={recordTask} onClose={() => setRecordTask(undefined)} onSaved={() => { setRecordTask(undefined); void load(); }} />
  </section>;
}
