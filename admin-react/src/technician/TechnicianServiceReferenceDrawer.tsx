import { useEffect, useState } from 'react';
import { Alert, Descriptions, Drawer, Empty, Spin, Tag, Typography } from 'antd';
import { getTechnicianServiceReference } from '../api';
import type { TechnicianServiceReferenceResponse } from './serviceReference';

export default function TechnicianServiceReferenceDrawer({ occupancyId, open, onClose }: { occupancyId: number | null; open: boolean; onClose: () => void }) {
  const [data, setData] = useState<TechnicianServiceReferenceResponse>();
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open || occupancyId === null) return;
    let active = true;
    setLoading(true); setFailed(false); setData(undefined);
    getTechnicianServiceReference(occupancyId)
      .then((response) => { if (active) setData(response.data); })
      .catch(() => { if (active) setFailed(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [occupancyId, open]);

  const record = data?.record;
  return <Drawer title="上次服务参考" placement="bottom" height="min(72vh, 560px)" open={open} onClose={onClose}>
    {loading ? <div className="technician-reference-state"><Spin /><Typography.Text type="secondary">正在读取已确认记录…</Typography.Text></div> : failed ? <Alert type="error" showIcon message="服务参考加载失败" description="请关闭后重试，或直接向顾客现场确认。" /> : !record ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={data?.message || '暂无顾客确认的历史服务参考，请现场询问'} /> : <div className="technician-reference-card">
      <Tag color="green">顾客已确认</Tag>
      <Descriptions column={1} size="small">
        <Descriptions.Item label="重点">{record.focus_areas.join('、') || '未记录'}</Descriptions.Item>
        <Descriptions.Item label="避开">{record.avoid_areas.join('、') || '未记录'}</Descriptions.Item>
        <Descriptions.Item label="力度">{record.force_preference || '未记录'}</Descriptions.Item>
        <Descriptions.Item label="温度">{record.temperature_preference || '未记录'}</Descriptions.Item>
        <Descriptions.Item label="反馈">{record.service_feedback || '未记录'}</Descriptions.Item>
        <Descriptions.Item label="下次">{record.next_visit_plan || '未记录'}</Descriptions.Item>
        <Descriptions.Item label="记录日期">{record.recorded_date || '未记录'}</Descriptions.Item>
      </Descriptions>
      <Alert type="info" showIcon message={record.prompt || '请本次服务前再次确认'} />
    </div>}
  </Drawer>;
}
