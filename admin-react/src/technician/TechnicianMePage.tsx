import { useEffect, useState } from 'react';
import { Avatar, Card, Descriptions, Empty, Spin, Tag } from 'antd';
import { getMyShifts, getTechnicianMe } from '../api';
import { technicianAccountStatusLabel, technicianEmploymentStatusLabel } from './technicianMobile';

export default function TechnicianMePage() {
  const [me, setMe] = useState<any>();
  const [shifts, setShifts] = useState<any[]>([]);
  useEffect(() => {
    void getTechnicianMe().then((res) => setMe(res.data));
    void getMyShifts(14).then((res) => setShifts(res.data?.items || [])).catch(() => setShifts([]));
  }, []);
  if (!me) return <div className="technician-loading"><Spin /></div>;
  const tech = me.technician || {};
  const staff = me.staff || {};
  const accountStatus = technicianAccountStatusLabel(staff.status);
  const employmentStatus = technicianEmploymentStatusLabel(tech.status);
  const accountColor = staff.status === 'active' ? 'green' : staff.status === 'disabled' || staff.status === 'resigned' ? 'red' : 'default';
  const employmentColor = tech.status === 'available' ? 'green' : tech.status === 'busy' ? 'gold' : tech.status === 'resigned' || tech.status === 'suspended' ? 'red' : 'default';
  return <div className="technician-me-page">
    <div className="technician-profile-hero"><Avatar size={64}>{(tech.name || staff.name || '技').slice(0, 1)}</Avatar><div><h1>{tech.name || staff.name || '技师'}</h1><p>{tech.level || '技师'} · <Tag color={employmentColor}>{employmentStatus}</Tag></p></div></div>
    <Card title="我的信息"><Descriptions column={1} size="small"><Descriptions.Item label="门店">{staff.store_name || me.store?.name || '当前门店'}</Descriptions.Item><Descriptions.Item label="技师等级">{tech.level || '—'}</Descriptions.Item><Descriptions.Item label="账号状态"><Tag color={accountColor}>{accountStatus}</Tag></Descriptions.Item><Descriptions.Item label="服务状态"><Tag color={employmentColor}>{employmentStatus}</Tag></Descriptions.Item></Descriptions></Card>
    <Card title="我的排班" style={{ marginTop: 12 }}>
      {shifts.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未来 14 天暂无排班" /> : shifts.map((shift: any) =>
        <div key={shift.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--hxy-border-subtle)' }}>
          <span>{shift.work_date}</span>
          <Tag color={shift.shift_type === 'off' ? 'default' : shift.shift_type === 'full' ? 'green' : 'blue'}>{shift.shift_label}</Tag>
          <span style={{ color: 'var(--hxy-text-secondary)' }}>{shift.start_time && shift.end_time ? `${shift.start_time} - ${shift.end_time}` : '—'}</span>
        </div>
      )}
    </Card>
  </div>;
}
