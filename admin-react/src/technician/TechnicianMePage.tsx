import { useEffect, useState } from 'react';
import { Avatar, Card, Descriptions, Spin, Tag } from 'antd';
import { getTechnicianMe } from '../api';

export default function TechnicianMePage() {
  const [me, setMe] = useState<any>();
  useEffect(() => { void getTechnicianMe().then((res) => setMe(res.data)); }, []);
  if (!me) return <div className="technician-loading"><Spin /></div>;
  const tech = me.technician || {}; const staff = me.staff || {};
  return <div className="technician-me-page"><div className="technician-profile-hero"><Avatar size={64}>{(tech.name || staff.name || '技').slice(0, 1)}</Avatar><div><h1>{tech.name || staff.name || '技师'}</h1><p>{tech.level || '技师'} · <Tag color={staff.status === 'active' ? 'green' : 'default'}>{staff.status === 'active' ? '在岗' : (staff.status || '未知')}</Tag></p></div></div><Card title="我的信息"><Descriptions column={1} size="small"><Descriptions.Item label="门店">{staff.store_name || me.store?.name || '当前门店'}</Descriptions.Item><Descriptions.Item label="技师等级">{tech.level || '—'}</Descriptions.Item><Descriptions.Item label="账号状态">{staff.status || '—'}</Descriptions.Item></Descriptions></Card></div>;
}
