import { useEffect, useRef, useState } from 'react';
import { App, Button, Checkbox, Drawer, Form, Input, Space, Typography } from 'antd';
import { createCustomerProfileRecord } from '../api';
import { technicianOrderItemLabel } from './technicianMobile';
import BodyMapNoteDrawer from './BodyMapNoteDrawer';
import './service-notebook.css';
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
  const { message, modal } = App.useApp();
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
  const requestClose = () => {
    if (savingRef.current) return;
    if (!hasInput) { onClose(); return; }
    modal.confirm({ title: '笔记还没有保存', content: '返回后可以继续填写；放弃将清除本次未保存的内容。', okText: '继续填写', cancelText: '放弃内容', onCancel: onClose, maskClosable: false, closable: false });
  };
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
  return <Drawer title="服务笔记" placement="bottom" height="94dvh" open={!!task}
    onClose={requestClose} maskClosable={false} keyboard={!saving}
    className="technician-profile-sheet technician-notebook" footer={<div className="technician-profile-sheet-actions">
      <Button size="large" disabled={saving || hasInput} onClick={() => void save({ recordingOutcome: 'no_additional_notes', customerConfirmed: false })}>本次无补充</Button>
      <Button type="primary" block size="large" loading={saving} disabled={saving || (!hasInput && !saveFailed)}
        onClick={() => saveFailed && lastValues.current ? void save(lastValues.current) : form.submit()}>{saveFailed ? '重试保存' : '保存快记'}</Button>
    </div>}>
    <Typography.Paragraph type="secondary">{position} · {summary || '本次服务'}</Typography.Paragraph>
    <Form form={form} layout="vertical" disabled={saving} onFinish={saveForm}
      onValuesChange={() => setSaveFailed(false)} initialValues={{ focusAreas: [], avoidAreas: [] }}>
      <section className="notebook-writing">
        <h2>记住这次，下次更好。</h2>
        <p>记下顾客的要求、有效的调整，或还没解决的事。</p>
        <Form.Item name="serviceNote" label="本次笔记">
          <Input.TextArea autoSize={{ minRows: 3, maxRows: 8 }} maxLength={200} showCount placeholder="例如：顾客说左肩轻一点更舒服，下次先问问是否还需要调整。" />
        </Form.Item>
      </section>
      <section className="notebook-preferences">
        <h3>顾客明确提出的要求</h3><p>有提到就选，没有可以留空。</p>
        <Form.Item name="communicationPreference" label="聊天"><Choices options={SERVICE_REFERENCE_OPTIONS.communication.filter(item => item.value !== 'explain_before_action')} /></Form.Item>
        <Form.Item name="forcePreference" label="力度"><Choices options={SERVICE_REFERENCE_OPTIONS.force} /></Form.Item>
        <Form.Item name="temperaturePreference" label="温度"><Choices options={SERVICE_REFERENCE_OPTIONS.temperature} /></Form.Item>
        <Form.Item name="focusAreas" label="重点照顾"><Choices multiple options={SERVICE_REFERENCE_OPTIONS.focusAreas} /></Form.Item>
        <Form.Item name="avoidAreas" label="需要避开"><Choices multiple options={SERVICE_REFERENCE_OPTIONS.avoidAreas} /></Form.Item>
      </section>
      <section className="notebook-followup">
        <h3>本次反馈与下次安排</h3>
        <Form.Item name="serviceFeedback" label="顾客反馈"><Choices options={SERVICE_REFERENCE_OPTIONS.feedback} /></Form.Item>
        <Form.Item name="nextVisitPlan" label="下次服务"><Choices options={SERVICE_REFERENCE_OPTIONS.nextVisit} /></Form.Item>
        <Button block size="large" disabled={saving} onClick={() => setBodyNoteOpen(true)}>{bodyMapNotes.length ? '查看 ' + bodyMapNotes.length + ' 条身体补充' : '需要记录身体情况'}</Button>
        <Checkbox checked={confirmation} disabled={saving} onChange={event => { setConfirmation(event.target.checked); setSaveFailed(false); }} style={{ marginTop: 16 }}>已向顾客复述并确认</Checkbox>
        <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>未勾选也可保存；补充文字仅留作本次服务记录。</Typography.Paragraph>
      </section>
    </Form>
    <BodyMapNoteDrawer open={bodyNoteOpen && !!task} value={bodyMapNotes}
      onChange={notes => { setBodyMapNotes(notes); setSaveFailed(false); }} onClose={() => setBodyNoteOpen(false)} context={position + ' · 顾客'} />
  </Drawer>;
}
