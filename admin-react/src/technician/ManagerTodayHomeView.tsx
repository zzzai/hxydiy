import { getManagerDaily, getManagerWorkbench } from '../api';
import './manager-home.css';

type Daily = Awaited<ReturnType<typeof getManagerDaily>>['data'];
type Workbench = Awaited<ReturnType<typeof getManagerWorkbench>>['data'];

function dateLabel() {
  const now = new Date();
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  return `${now.getMonth() + 1}月${now.getDate()}日 · ${weekdays[now.getDay()]}`;
}

export default function ManagerTodayHomeView({ daily, workbench, onOpenOps, onOpenTasks, onOpenCoupons, onOpenRedeemCoupon, onOpenCouponHistory }: {
  daily: Daily | null;
  workbench: Workbench | null;
  onOpenOps: () => void;
  onOpenTasks: () => void;
  onOpenCoupons: () => void;
  onOpenRedeemCoupon: () => void;
  onOpenCouponHistory: () => void;
}) {
  const done = daily?.completion.areas_done || 0;
  const hasMeeting = daily?.completion.has_meeting || false;
  const attention = workbench?.summary?.attention || 0;
  const tasks: Array<{ key: string; icon: string; title: string; note: string; badge: string; tone: string; onClick: () => void }> = [];

  if (done < 5) tasks.push({ key: 'inspection', icon: '巡', title: '巡检照片', note: `5 个区域，完成 ${done} 个`, badge: `${done}/5`, tone: 'warn', onClick: onOpenOps });
  if (!hasMeeting) tasks.push({ key: 'meeting', icon: '会', title: '晨会录音', note: '今天还没有录音', badge: '未录', tone: 'warn', onClick: onOpenOps });
  if (attention > 0) tasks.push({ key: 'attention', icon: '待', title: '待处理事项', note: '订单和现场提醒', badge: String(attention), tone: 'normal', onClick: onOpenTasks });

  return <div className="manager-home">
    <div className="manager-home-lead">
      <p>{dateLabel()}</p>
      <h1>{tasks.length ? <>今天先做<br />这 {tasks.length} 件</> : '今天没有待处理'}</h1>
      <span>{tasks.length ? '做完巡检、晨会和待处理，今天的现场就稳了。' : '巡检、晨会和处理事项都已完成。'}</span>
    </div>

    {tasks.length ? <section className="manager-home-section">
      <div className="manager-home-label"><span>需要你处理</span><small>按优先级</small></div>
      <div className="manager-home-tasks">
        {tasks.map((task) => <button type="button" key={task.key} className="manager-home-task" onClick={task.onClick}>
          <span className={`manager-home-task-icon ${task.tone}`}>{task.icon}</span>
          <span className="manager-home-task-copy"><strong>{task.title}</strong><small>{task.note}</small></span>
          <span className="manager-home-task-side"><em className={task.tone === 'warn' ? 'warn' : 'normal'}>{task.badge}</em><i>›</i></span>
        </button>)}
      </div>
    </section> : null}

    <section className="manager-home-orders" aria-label="今日订单">
      <div><strong>{workbench?.summary?.today_orders ?? '—'}</strong><span>今日订单</span></div>
      <div><strong>{workbench?.summary?.waiting_service ?? '—'}</strong><span>待服务</span></div>
      <div><strong>{workbench?.summary?.in_service ?? '—'}</strong><span>服务中</span></div>
    </section>

    <section className="manager-home-section">
      <div className="manager-home-label"><span>常用</span><small>本店</small></div>
      <div className="manager-home-quick">
        <button type="button" onClick={onOpenCoupons}><b>券</b><span>发券</span></button>
        <button type="button" onClick={onOpenRedeemCoupon}><b>核</b><span>核销券</span></button>
        <button type="button" onClick={onOpenCouponHistory}><b>记</b><span>券记录</span></button>
      </div>
    </section>

    {daily?.status === 'submitted' ? <p className="manager-home-done">今日巡检已提交</p> : <p className="manager-home-note">数据每 15 秒刷新一次，现场状态以系统为准。</p>}
  </div>;
}
