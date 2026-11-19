import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Alert, Avatar, Button, Descriptions, Empty, Spin, Tag } from 'antd';
import { getMyShifts, getTechnicianMe } from '../api';
import { technicianAccountStatusLabel, technicianEmploymentStatusLabel } from './technicianMobile';
import { useTechnicianSession } from './useTechnicianSession';

export default function TechnicianMePage({ learningEntry }: { learningEntry?: ReactNode }) {
  const [me, setMe] = useState<any>();
  const [shifts, setShifts] = useState<any[]>([]);
  const [failed, setFailed] = useState(false);
  const [shiftsFailed, setShiftsFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const current = useTechnicianSession();
  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    setShiftsFailed(false);
    const [profile, schedule] = await Promise.allSettled([getTechnicianMe(), getMyShifts(14)]);
    if (!current()) return;
    if (profile.status === 'fulfilled') setMe(profile.value.data);
    else setFailed(true);
    if (schedule.status === 'fulfilled') setShifts(schedule.value.data?.items || []);
    else setShiftsFailed(true);
    setLoading(false);
  }, [current]);
  useEffect(() => { void load(); }, [load]);
  if (loading) return <div className="technician-loading" role="status" aria-label="正在加载个人信息"><Spin /></div>;
  if (failed || !me) return <Alert type="error" showIcon message="个人信息加载失败" description="请检查网络后重试。" action={<Button onClick={() => void load()}>重试</Button>} />;
  const tech = me.technician || {};
  const staff = me.staff || {};
  const accountStatus = technicianAccountStatusLabel(staff.status);
  const employmentStatus = technicianEmploymentStatusLabel(tech.status);
  const accountColor = staff.status === 'active' ? 'green' : staff.status === 'disabled' || staff.status === 'resigned' ? 'red' : 'default';
  const employmentColor = tech.status === 'available' ? 'green' : tech.status === 'busy' ? 'gold' : tech.status === 'resigned' || tech.status === 'suspended' ? 'red' : 'default';
  return <div className="technician-me-page">
    <div className="technician-page-title"><h1>我的</h1></div>
    <div className="technician-profile-hero"><Avatar size={48}>{(tech.name || staff.name || '技').slice(0, 1)}</Avatar><div><h2>{tech.name || staff.name || '技师'}</h2><p>{tech.level || '技师'} · <Tag color={employmentColor}>{employmentStatus}</Tag></p></div></div>
    {learningEntry}
    <section className="technician-account-details" aria-labelledby="technician-account-heading">
      <h2 id="technician-account-heading">账号信息</h2>
      <Descriptions column={1} size="small"><Descriptions.Item label="门店">{staff.store_name || me.store?.name || '当前门店'}</Descriptions.Item><Descriptions.Item label="技师等级">{tech.level || '—'}</Descriptions.Item><Descriptions.Item label="账号状态"><Tag color={accountColor}>{accountStatus}</Tag></Descriptions.Item><Descriptions.Item label="服务状态"><Tag color={employmentColor}>{employmentStatus}</Tag></Descriptions.Item></Descriptions>
    </section>
    <details className="technician-schedule"><summary><span>我的排班</span><small>未来 14 天</small></summary>
      {shiftsFailed ? <Alert type="error" message="排班加载失败" action={<Button onClick={() => void load()}>重试</Button>} /> : shifts.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未来 14 天暂无排班" /> : shifts.map((shift: any) =>
        <div key={shift.id} className="technician-shift-row"><span>{shift.work_date}</span><Tag color={shift.shift_type === 'off' ? 'default' : shift.shift_type === 'full' ? 'green' : 'blue'}>{shift.shift_label}</Tag><span>{shift.start_time && shift.end_time ? [shift.start_time, shift.end_time].join(' - ') : '—'}</span></div>
      )}
    </details>
  </div>;
}
