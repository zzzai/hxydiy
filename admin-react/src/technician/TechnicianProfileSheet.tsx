import { useEffect, useRef, useState } from 'react';
import { App, Button, Drawer, Form, Input, Radio, Switch, Tag, Typography } from 'antd';
import { createCustomerProfileRecord } from '../api';
import { technicianOrderItemLabel } from './technicianMobile';
import { SERVICE_REFERENCE_OPTIONS, buildServiceReferencePayload, hasServiceReferenceInput, type ServiceReferenceInput } from './serviceReference';

function makeIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() || `profile-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function TechnicianProfileSheet({ task, onClose, onSaved }: { task: any; onClose: () => void; onSaved: () => void }) {
  const [form] = Form.useForm<ServiceReferenceInput>();
  const { message } = App.useApp();
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const idempotencyKey = useRef(makeIdempotencyKey());

  useEffect(() => {
    form.resetFields();
    idempotencyKey.current = makeIdempotencyKey();
    setSaveFailed(false);
  }, [form, task]);

  const save = async (values: ServiceReferenceInput) => {
    const customerId = task?.customer?.id ?? task?.user_id;
    if (!customerId || !task?.selection_session_id || saving) return;
    if (!hasServiceReferenceInput(values)) {
      message.warning('请至少选择或填写一项服务参考');
      return;
    }
    setSaving(true);
    setSaveFailed(false);
    try {
      await createCustomerProfileRecord(buildServiceReferencePayload(customerId, task.selection_session_id, values), idempotencyKey.current);
      message.success('服务参考已记录');
      onSaved();
    } catch {
      setSaveFailed(true);
      message.error('保存失败，请检查网络后重试');
    } finally {
      setSaving(false);
    }
  };

  const toggleValue = (field: 'focusAreas' | 'avoidAreas', value: string, checked: boolean) => {
    const current = (form.getFieldValue(field) || []) as string[];
    form.setFieldValue(field, checked ? [...current, value] : current.filter((item) => item !== value));
  };
  const summary = (task?.items || []).map(technicianOrderItemLabel).filter(Boolean).join('、') || '顾客暂未填写项目';
  const position = task?.room_name || task?.room_code || task?.position_name || '当前服务位';

  return <Drawer title="本次服务参考" placement="bottom" height="min(94vh, 820px)" open={!!task} onClose={saving ? undefined : onClose} className="technician-profile-sheet" footer={<div className="technician-profile-sheet-actions">
    <Button block size="large" onClick={onClose} disabled={saving}>暂不记录</Button>
    <Button type="primary" block size="large" onClick={() => form.submit()} loading={saving} disabled={saving}>{saveFailed ? '重试保存' : '保存服务参考'}</Button>
  </div>}>
    <div className="technician-profile-context">
      <div><Typography.Text strong>{position}</Typography.Text><Tag color="blue">已完成</Tag></div>
      <Typography.Text type="secondary">{task?.customer?.nickname || '顾客'} · {summary}</Typography.Text>
      <Typography.Paragraph type="secondary">点选即可，建议当面复述确认；仅作到店服务参考。</Typography.Paragraph>
    </div>
    <Form form={form} layout="vertical" onFinish={save} initialValues={{ focusAreas: [], avoidAreas: [], customerConfirmed: false }}>
      <Form.Item label="本次重点" shouldUpdate={(before, after) => before.focusAreas !== after.focusAreas}>
        {() => <div className="technician-tag-list">{SERVICE_REFERENCE_OPTIONS.focusAreas.map((option) => <Tag.CheckableTag key={option.value} checked={(form.getFieldValue('focusAreas') || []).includes(option.value)} onChange={(checked) => toggleValue('focusAreas', option.value, checked)}>{option.label}</Tag.CheckableTag>)}</div>}
      </Form.Item>
      <Form.Item label="避开或谨慎" shouldUpdate={(before, after) => before.avoidAreas !== after.avoidAreas}>
        {() => <div className="technician-tag-list">{SERVICE_REFERENCE_OPTIONS.avoidAreas.map((option) => <Tag.CheckableTag key={option.value} checked={(form.getFieldValue('avoidAreas') || []).includes(option.value)} onChange={(checked) => toggleValue('avoidAreas', option.value, checked)}>{option.label}</Tag.CheckableTag>)}</div>}
      </Form.Item>
      <Form.Item name="forcePreference" label="力度偏好"><Radio.Group optionType="button" buttonStyle="solid" options={SERVICE_REFERENCE_OPTIONS.force} /></Form.Item>
      <Form.Item name="temperaturePreference" label="温度偏好"><Radio.Group optionType="button" buttonStyle="solid" options={SERVICE_REFERENCE_OPTIONS.temperature} /></Form.Item>
      <Form.Item name="serviceFeedback" label="服务反馈"><Radio.Group optionType="button" buttonStyle="solid" options={SERVICE_REFERENCE_OPTIONS.feedback} /></Form.Item>
      <Form.Item name="nextVisitPlan" label="下次建议"><Radio.Group optionType="button" buttonStyle="solid" options={SERVICE_REFERENCE_OPTIONS.nextVisit} /></Form.Item>
      <Form.Item name="customerConfirmed" label="已向顾客复述并确认" valuePropName="checked"><Switch checkedChildren="已确认" unCheckedChildren="未确认" /></Form.Item>
      <Form.Item name="quote" label="顾客原话（可选）"><Input.TextArea rows={2} maxLength={100} showCount placeholder="只记服务偏好，不记诊断、联系方式或隐私信息" /></Form.Item>
    </Form>
  </Drawer>;
}
