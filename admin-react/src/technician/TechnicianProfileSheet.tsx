import { useEffect, useRef, useState } from 'react';
import { App, Button, Checkbox, Drawer, Form, Input, Space, Typography } from 'antd';
import { createCustomerProfileRecord } from '../api';
import { technicianOrderItemLabel } from './technicianMobile';
import BodyMapNoteDrawer from './BodyMapNoteDrawer';
import { SERVICE_REFERENCE_OPTIONS, buildServiceReferenceV5Payload, hasServiceReferenceInput, type ServiceReferenceInput, type V5BodyServiceNote } from './serviceReference';

function Choices({ value, onChange, options, multiple = false }: {
  value?: string | string[]; onChange?: (value: any) => void;
  options: ReadonlyArray<{ value: string; label: string }>; multiple?: boolean;
}) {
  return <Space wrap size={[8, 8]}>{options.map(option => {
    const selected = multiple ? Array.isArray(value) && value.includes(option.value) : value === option.value;
    return <Button key={option.value} size="large" type={selected ? 'primary' : 'default'} aria-pressed={selected}
      onClick={() => onChange?.(multiple
        ? (selected ? (value as string[]).filter(item => item !== option.value) : [...(Array.isArray(value) ? value : []), option.value])
        : selected ? undefined : option.value)}>{option.label}</Button>;
  })}</Space>;
}

export default function TechnicianProfileSheet({ task, onClose, onSaved }: { task: any; onClose: () => void; onSaved: () => void }) {
  const [form] = Form.useForm<ServiceReferenceInput>();
  const values = Form.useWatch([], form) as ServiceReferenceInput | undefined;
  const { message } = App.useApp();
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const [confirmation, setConfirmation] = useState(false);
  const [bodyNoteOpen, setBodyNoteOpen] = useState(false);
  const [bodyMapNotes, setBodyMapNotes] = useState<V5BodyServiceNote[]>([]);
  const idempotencyKey = useRef(crypto.randomUUID());
  const lastPayloadSignature = useRef<string | null>(null);
  const lastValues = useRef<ServiceReferenceInput | null>(null);
  const taskKey = task?.selection_session_id;

  useEffect(() => {
    form.resetFields();
    idempotencyKey.current = crypto.randomUUID();
    lastPayloadSignature.current = null;
    lastValues.current = null;
    setSaveFailed(false);
    setConfirmation(false);
    setBodyMapNotes([]);
    setBodyNoteOpen(false);
  }, [form, taskKey]);

  const hasInput = Boolean(values && (hasServiceReferenceInput(values) || values.serviceNote?.trim()) || bodyMapNotes.length);
  const save = async (input: ServiceReferenceInput) => {
    const customerId = task?.customer?.id ?? task?.user_id;
    if (!customerId || !task?.selection_session_id || savingRef.current) return;
    if (!hasServiceReferenceInput(input) && !input.serviceNote?.trim() && !input.bodyMapNotes?.length && !input.recordingOutcome) return;
    const payload = buildServiceReferenceV5Payload(customerId, task.selection_session_id, input);
    const payloadSignature = JSON.stringify(payload);
    if (lastPayloadSignature.current !== null && lastPayloadSignature.current !== payloadSignature) idempotencyKey.current = crypto.randomUUID();
    lastPayloadSignature.current = payloadSignature;
    lastValues.current = input;
    savingRef.current = true;
    setSaving(true);
    setSaveFailed(false);
    try {
      await createCustomerProfileRecord(payload, idempotencyKey.current);
      message.success(input.recordingOutcome ? '已记录：本次无补充' : '服务快记已保存');
      onSaved();
    } catch {
      setSaveFailed(true);
      message.error('未保存成功，内容已保留；请检查网络或填写内容后重试');
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const saveForm = (input: ServiceReferenceInput) => void save({ ...input, bodyMapNotes, customerConfirmed: confirmation === true });
  const summary = (task?.items || []).map(technicianOrderItemLabel).filter(Boolean).join('、');
  const position = task?.room_name || task?.room_code || task?.position_name || '当前服务位';
  const outcome = values?.serviceFeedback;
  return <Drawer title="给下次服务留句话" placement="bottom" height="min(94vh, 820px)" open={!!task}
    onClose={saving ? undefined : onClose} maskClosable={!saving} keyboard={!saving}
    className="technician-profile-sheet" footer={<div className="technician-profile-sheet-actions">
      <Button size="large" onClick={onClose} disabled={saving}>稍后记录</Button>
      <Button type="primary" block size="large" loading={saving} disabled={saving || (!hasInput && !saveFailed)}
        onClick={() => saveFailed && lastValues.current ? void save(lastValues.current) : form.submit()}>{saveFailed ? '重试保存' : '保存快记'}</Button>
    </div>}>
    <Typography.Paragraph type="secondary">{position} · {summary || '本次服务'}</Typography.Paragraph>
    <Form form={form} layout="vertical" disabled={saving} onFinish={saveForm}
      onValuesChange={() => setSaveFailed(false)} initialValues={{ focusAreas: [], avoidAreas: [] }}>
      <Form.Item name="serviceFeedback" hidden><Input /></Form.Item>
      <Typography.Title level={4}>这次服务，顾客感觉怎么样？</Typography.Title>
      <Space direction="vertical" style={{ display: 'flex' }} size={10}>
        <Button block size="large" onClick={() => void save({ recordingOutcome: 'no_additional_notes', customerConfirmed: false })}>顺利完成</Button>
        <Button block size="large" type={outcome === 'better_after_adjustment' ? 'primary' : 'default'} onClick={() => form.setFieldValue('serviceFeedback', 'better_after_adjustment')}>调整后更舒服</Button>
        <Button block size="large" type={outcome === 'adjust_next_time' ? 'primary' : 'default'} onClick={() => form.setFieldValue('serviceFeedback', 'adjust_next_time')}>下次需注意</Button>
      </Space>
      {outcome && <>
        <Form.Item label={outcome === 'better_after_adjustment' ? '本次怎么调整更舒服' : '下次先留意什么'} style={{ marginTop: 24 }}>
          <Form.Item name="focusAreas" noStyle><Choices multiple options={SERVICE_REFERENCE_OPTIONS.focusAreas} /></Form.Item>
          <Form.Item name="forcePreference" noStyle><Choices options={SERVICE_REFERENCE_OPTIONS.force} /></Form.Item>
          {outcome === 'adjust_next_time' && <><Form.Item name="avoidAreas" noStyle><Choices multiple options={SERVICE_REFERENCE_OPTIONS.avoidAreas} /></Form.Item><Form.Item name="communicationPreference" noStyle><Choices options={SERVICE_REFERENCE_OPTIONS.communication} /></Form.Item><Form.Item name="nextVisitPlan" noStyle><Choices options={SERVICE_REFERENCE_OPTIONS.nextVisit} /></Form.Item></>}
          {outcome === 'better_after_adjustment' && <Form.Item name="temperaturePreference" noStyle><Choices options={SERVICE_REFERENCE_OPTIONS.temperature} /></Form.Item>}
        </Form.Item>
        <Form.Item name="serviceNote" label="补一句（可不填)">
          <Input.TextArea rows={2} maxLength={200} showCount placeholder="例如：左肩轻一点更舒服；下次先确认" />
        </Form.Item>
        <Button block size="large" disabled={saving} onClick={() => setBodyNoteOpen(true)}>{bodyMapNotes.length ? '查看 ' + bodyMapNotes.length + ' 条身体补充' : '需要记录身体情况'}</Button>
        <Checkbox checked={confirmation} disabled={saving} onChange={event => { setConfirmation(event.target.checked); setSaveFailed(false); }} style={{ marginTop: 16 }}>已向顾客复述并确认</Checkbox>
        <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>未勾选也可保存；补充文字仅留作本次服务记录。</Typography.Paragraph>
      </>}
    </Form>
    <BodyMapNoteDrawer open={bodyNoteOpen && !!task} value={bodyMapNotes}
      onChange={notes => { setBodyMapNotes(notes); setSaveFailed(false); }} onClose={() => setBodyNoteOpen(false)} context={position + ' · 顾客'} />
  </Drawer>;
}
