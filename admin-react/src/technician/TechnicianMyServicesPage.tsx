import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Empty, Spin, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import { finishTechnicianService, getTechnicianMyTasks } from '../api';
import type { TechnicianCustomerTask } from '../technicianCustomer';
import { createTechnicianActionRunner, technicianOrderItemLabel, technicianStatusLabel } from './technicianMobile';
import TechnicianCustomerPanel from './TechnicianCustomerPanel';
import TechnicianProfileSheet from './TechnicianProfileSheet';
import { useTechnicianSession } from './useTechnicianSession';
import './technician-customer.css';

export default function TechnicianMyServicesPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const current = useTechnicianSession();
  const [tasks, setTasks] = useState<TechnicianCustomerTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [customer, setCustomer] = useState<number>();
  const [record, setRecord] = useState<TechnicianCustomerTask>();
  const [acting, setActing] = useState<number>();
  const loadingRef = useRef(false);
  const runner = useRef(createTechnicianActionRunner()).current;
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
  const finish = async (task: TechnicianCustomerTask) => {
    if (runner.isRunning('finish', task.occupancy_id)) return;
    setActing(task.occupancy_id);
    try {
      await runner.run('finish', task.occupancy_id, finishTechnicianService);
      if (!current()) return;
      message.success('服务已结束');
      if (task.user_id) setRecord({ ...task, occupancy_status: 'post_service_present' });
      await load();
    } catch { /* The shared interceptor handles current-session errors. */ }
    finally { if (current()) setActing(undefined); }
  };
  return <section className="technician-my-services">
    <header><h1>我的服务</h1><p>查看本人正在服务和服务后尚未离店的顾客。</p></header>
    <Button block onClick={() => navigate('/positions')}>查看门店服务位</Button>
    {error && <Alert type="error" message={error} action={<Button onClick={() => void load()}>重试</Button>} />}
    {loading ? <Spin /> : tasks.length ? tasks.map((task) => <article key={task.occupancy_id} className="technician-customer-entry">
      <h2>{task.room_name || '本次服务'} <Tag>{technicianStatusLabel(task.occupancy_status)}</Tag></h2>
      <p>{task.items.map(technicianOrderItemLabel).filter(Boolean).join('、') || '未记录项目'}</p>
      <div className="technician-my-service-actions">
        <Button onClick={() => setCustomer(task.occupancy_id)}>查看顾客资料</Button>
        {task.occupancy_status === 'in_service' ? <Button type="primary" loading={acting === task.occupancy_id} onClick={() => void finish(task)}>服务结束</Button> : <Button disabled={!task.user_id} onClick={() => navigate('/history')}>查看服务记录</Button>}
      </div>
      {!task.user_id && <p>匿名服务可正常完成，暂未关联顾客资料。</p>}
    </article>) : <Empty description="目前没有本人正在服务的顾客" />}
    {customer !== undefined && <TechnicianCustomerPanel key={customer} occupancyId={customer} onClose={closeCustomer} />}
    {record && <TechnicianProfileSheet key={record.selection_session_id} task={{ ...record, customer: { id: record.user_id }, status: 'completed', completed_by_me: true }} onClose={() => setRecord(undefined)} onSaved={() => { if (current()) { setRecord(undefined); void load(); } }} />}
  </section>;
}
