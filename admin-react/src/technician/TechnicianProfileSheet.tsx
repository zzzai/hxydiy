import { useEffect, useRef, useState } from 'react';
import { App, Button, Drawer, Form, Input, Radio, Select, Tag, Typography } from 'antd';
import { createCustomerProfileRecord } from '../api';
import { technicianOrderItemLabel } from './technicianMobile';

const OBSERVATION_TAGS = ['肩颈紧张', '腰部不适', '腿部酸胀', '局部紧绷', '放松需求'];
const FORCE_TAGS = ['偏好轻柔力度', '偏好中等力度', '偏好强力力度'];
const SOURCE_OPTIONS = [
  { label: '顾客自述', value: 'customer_statement' },
  { label: '服务观察', value: 'service_observation' },
  { label: '两者都有', value: 'both' },
];
const profileOptions = {
  age_range: ['18-25', '26-35', '36-45', '46岁以上', '不确定'],
  gender: ['男', '女', '不记录'],
  body_type: ['偏瘦', '标准', '偏壮', '不记录'],
  occupation: ['久坐', '久站', '体力工作', '其他', '不记录'],
};

function makeIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() || `profile-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function TechnicianProfileSheet({ task, onClose, onSaved }: { task: any; onClose: () => void; onSaved: () => void }) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const idempotencyKey = useRef(makeIdempotencyKey());

  useEffect(() => {
    form.resetFields();
    idempotencyKey.current = makeIdempotencyKey();
    setSaveFailed(false);
  }, [form, task]);

  const save = async (values: { source: 'customer_statement' | 'service_observation' | 'both'; signals?: string[]; age_range?: string; gender?: string; body_type?: string; occupation?: string; service_note?: string }) => {
    const customerId = task?.customer?.id ?? task?.user_id;
    if (!customerId || !task?.selection_session_id || saving) return;
    setSaving(true);
    setSaveFailed(false);
    const profile: Record<string, string> = {};
    for (const key of ['age_range', 'gender', 'body_type', 'occupation'] as const) {
      const value = values[key];
      if (value && value !== '不记录') profile[key] = value;
    }
    try {
      await createCustomerProfileRecord({
        user_id: customerId,
        selection_session_id: task.selection_session_id,
        source: values.source || 'customer_statement',
        profile,
        signals: values.signals || [],
        note: values.service_note || '',
      }, idempotencyKey.current);
      message.success('服务参考已记录');
      onSaved();
    } catch {
      setSaveFailed(true);
      message.error('保存失败，请检查网络后重试');
    } finally {
      setSaving(false);
    }
  };

  const summary = (task?.items || []).map(technicianOrderItemLabel).filter(Boolean).join('、') || '顾客暂未填写项目';
  const position = task?.room_name || task?.room_code || task?.position_name || '当前服务位';

  return <Drawer
    title="服务参考"
    placement="bottom"
    height="min(94vh, 760px)"
    open={!!task}
    onClose={saving ? undefined : onClose}
    className="technician-profile-sheet"
    footer={<div className="technician-profile-sheet-actions">
      <Button block size="large" onClick={onClose} disabled={saving}>暂不记录</Button>
      <Button type="primary" block size="large" onClick={() => form.submit()} loading={saving} disabled={saving}>{saveFailed ? '重试保存' : '保存服务参考'}</Button>
    </div>}
  >
    <div className="technician-profile-context">
      <div><Typography.Text strong>{position}</Typography.Text><Tag color="blue">已完成</Tag></div>
      <Typography.Text type="secondary">{task?.customer?.nickname || '顾客'} · {summary}</Typography.Text>
      <Typography.Paragraph type="secondary">仅作到店服务参考，不构成医疗建议</Typography.Paragraph>
    </div>
    <Form form={form} layout="vertical" onFinish={save} initialValues={{ source: 'customer_statement' }}>
      <Form.Item name="source" label="记录来源" rules={[{ required: true, message: '请选择记录来源' }]}>
        <Radio.Group options={SOURCE_OPTIONS} optionType="button" buttonStyle="solid" />
      </Form.Item>
      <Form.Item name="age_range" label="年龄段"><Select allowClear placeholder="不记录" options={profileOptions.age_range.map((value) => ({ label: value, value }))} /></Form.Item>
      <Form.Item name="gender" label="性别"><Radio.Group options={profileOptions.gender.map((value) => ({ label: value, value }))} /></Form.Item>
      <Form.Item name="body_type" label="体型"><Radio.Group options={profileOptions.body_type.map((value) => ({ label: value, value }))} /></Form.Item>
      <Form.Item name="occupation" label="职业场景"><Radio.Group options={profileOptions.occupation.map((value) => ({ label: value, value }))} /></Form.Item>
      <Form.Item name="signals" label="服务关注"><div className="technician-tag-list">{OBSERVATION_TAGS.map((tag) => <Form.Item key={tag} noStyle shouldUpdate={(prev, next) => prev.signals !== next.signals}>{({ getFieldValue, setFieldsValue }) => { const selected = (getFieldValue('signals') || []).includes(tag); return <Tag.CheckableTag checked={selected} onChange={(checked) => { const current = getFieldValue('signals') || []; setFieldsValue({ signals: checked ? [...current, tag] : current.filter((item: string) => item !== tag) }); }}>{tag}</Tag.CheckableTag>; }}</Form.Item>)}</div></Form.Item>
      <Form.Item name="force_signal" label="力度偏好"><Radio.Group options={FORCE_TAGS.map((value) => ({ label: value, value }))} onChange={(event) => form.setFieldsValue({ signals: [...(form.getFieldValue('signals') || []).filter((item: string) => !FORCE_TAGS.includes(item)), event.target.value] })} /></Form.Item>
      <Form.Item name="service_note" label="服务注意事项"><Input.TextArea rows={4} maxLength={500} showCount placeholder="填写顾客自述、服务观察和注意事项，不填写诊断或治疗结论" /></Form.Item>
    </Form>
  </Drawer>;
}
