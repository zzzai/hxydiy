import { Button, Tag } from 'antd';
import { AudioOutlined, CameraOutlined, CheckCircleFilled, CoffeeOutlined, ShopOutlined, StarOutlined, TeamOutlined, GiftOutlined } from '@ant-design/icons';
import { getManagerDaily, getManagerTeam, getManagerWorkbench } from '../api';

type Daily = Awaited<ReturnType<typeof getManagerDaily>>['data'];
type Team = Awaited<ReturnType<typeof getManagerTeam>>['data'];
type Workbench = Awaited<ReturnType<typeof getManagerWorkbench>>['data'];

export default function ManagerTodayView({ daily, team, workbench, onOpenFloor, onOpenOps, onOpenTeam, onOpenReviews, onOpenCoupons, onOpenOrders, onOpenTasks }: {
  daily: Daily | null; team: Team | null; workbench: Workbench | null;
  onOpenFloor: () => void; onOpenOps: () => void; onOpenTeam: () => void;
  onOpenReviews: () => void; onOpenCoupons: () => void; onOpenOrders: () => void; onOpenTasks: () => void;
}) {
  const done = daily?.completion.areas_done || 0;
  const hasMeeting = daily?.completion.has_meeting || false;
  const completion = Math.round(((done + (hasMeeting ? 1 : 0)) / 6) * 100);
  const overdue = team?.summary.overdue || 0;
  const attention = workbench?.summary?.attention || 0;

  return <div className="manager-p0-stack">
    <section className="manager-p0-hero">
      <div className="manager-p0-hero-top"><div><small>今日经营</small><h1>早上好，店长</h1></div><Tag color={daily?.status === 'submitted' ? 'green' : 'gold'}>{daily?.status === 'submitted' ? '今日已提交' : '进行中'}</Tag></div>
      <div className="manager-p0-ring-row">
        <div className="manager-p0-ring" style={{ background: `conic-gradient(#145545 ${completion}%, #e7f0eb ${completion}% 100%)` }}><div><strong>{done}<small>/5</small></strong><span>区域</span></div></div>
        <div className="manager-p0-hero-copy"><strong>{hasMeeting ? '晨会已录音' : '晨会待录音'}</strong><p>{daily?.status === 'submitted' ? '今天的经营动作已经留痕。' : '照片、晨会、评价，一件件完成。'}</p><Button size="small" onClick={onOpenOps}>继续完成</Button></div>
      </div>
    </section>

    <div className="manager-p0-stat-grid">
      <button type="button" onClick={onOpenOrders}><strong>{workbench?.summary?.today_orders ?? '—'}</strong><span>今日订单</span></button>
      <button type="button" onClick={onOpenTasks}><strong>{workbench?.summary?.waiting_service ?? '—'}</strong><span>待服务</span></button>
      <span><strong>{workbench?.summary?.in_service ?? '—'}</strong><span>服务中</span></span>
      <button type="button" className={attention ? 'warn' : ''} onClick={onOpenTasks}><strong>{attention}</strong><span>需处理</span></button>
    </div>

    <div className="manager-p0-quick-grid">
      <button type="button" onClick={onOpenOps}><CameraOutlined /><strong>拍照巡检</strong><small>5 个区域</small></button>
      <button type="button" onClick={onOpenOps}><AudioOutlined /><strong>开会录音</strong><small>晨会 / 交接</small></button>
      <button type="button" onClick={onOpenCoupons}><GiftOutlined /><strong>发券</strong><small>100 张上限</small></button>
      <button type="button" onClick={onOpenReviews}><StarOutlined /><strong>看评价</strong><small>本店评价</small></button>
    </div>

    <section className="manager-p0-card manager-p0-floor-mini" onClick={onOpenFloor}>
      <div className="manager-p0-card-head"><div><small>现场</small><h3>沙发位与区域</h3></div><span className="manager-p0-link">全部 <ShopOutlined /></span></div>
      <div className="manager-p0-sofa-row">{['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((item) => <span key={item}>{item}</span>)}</div>
      <p className="manager-p0-muted">查看实时现场；座位状态由系统自动生成。</p>
    </section>

    <section className="manager-p0-card" onClick={onOpenTeam}>
      <div className="manager-p0-card-head"><div><small>团队</small><h3>本周学习</h3></div><span className="manager-p0-link">{team?.summary.on_track || 0}/{team?.summary.staff_count || 0} 达标 <TeamOutlined /></span></div>
      <div className="manager-p0-team-row">{team?.technicians.slice(0, 4).map((tech: Team['technicians'][number]) => <div key={tech.staff_id} className={tech.overdue ? 'warn' : ''}><span>{tech.name.slice(0, 1)}</span><strong>{tech.name}</strong><small>{tech.progress}%</small></div>)}</div>
      {overdue > 0 ? <p className="manager-p0-attention"><CoffeeOutlined /> {overdue} 人学习/考核待跟进</p> : <p className="manager-p0-muted"><CheckCircleFilled /> 本周学习进度正常</p>}
    </section>

    {(attention > 0 || overdue > 0) && <section className="manager-p0-alert"><strong>今天有 {attention + overdue} 件事需要你</strong><p>{attention ? `${attention} 条订单/评价待处理` : ''}{attention && overdue ? ' · ' : ''}{overdue ? `${overdue} 人学习逾期` : ''}</p></section>}
  </div>;
}
