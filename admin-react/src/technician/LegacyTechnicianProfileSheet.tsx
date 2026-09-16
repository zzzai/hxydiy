import { useEffect, useRef, useState } from 'react';
import { App, Button, Checkbox, Drawer, Form, Input, Space, Typography } from 'antd';
import { createCustomerProfileRecord } from '../api';
import { technicianOrderItemLabel } from './technicianMobile';
import BodyMapNoteDrawer from './BodyMapNoteDrawer';
import './service-notebook.css';
import { SERVICE_REFERENCE_OPTIONS, buildServiceReferenceV5Payload, hasServiceReferenceInput, type ServiceReferenceInput, type V5BodyServiceNote } from './serviceReference';

type CorrectionFormValues = ServiceReferenceInput & { correctionReason?: string };

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function correctionFormValues(record: any): CorrectionFormValues {
  const profile = asRecord(record?.profile);
  const reported = asRecord(profile.customer_reported);
  const observed = asRecord(profile.technician_observed);
  const nextVisit = asRecord(profile.next_visit);
  return {
    communicationPreference: typeof reported.communication_preference === 'string' ? reported.communication_preference as CorrectionFormValues['communicationPreference'] : undefined,
    focusAreas: stringList(reported.focus_areas) as CorrectionFormValues['focusAreas'],
    avoidAreas: stringList(reported.avoid_areas) as CorrectionFormValues['avoidAreas'],
    forcePreference: typeof reported.force_preference === 'string' ? reported.force_preference as CorrectionFormValues['forcePreference'] : undefined,
    temperaturePreference: typeof reported.temperature_preference === 'string' ? reported.temperature_preference as CorrectionFormValues['temperaturePreference'] : undefined,
    serviceAdjustments: stringList(observed.service_adjustments) as CorrectionFormValues['serviceAdjustments'],
    serviceFeedback: typeof observed.service_feedback === 'string' ? observed.service_feedback as CorrectionFormValues['serviceFeedback'] : undefined,
    serviceNote: typeof observed.service_note === 'string' ? observed.service_note : undefined,
    nextVisitPlan: typeof nextVisit.plan === 'string' ? nextVisit.plan as CorrectionFormValues['nextVisitPlan'] : undefined,
  };
}

function correctionBodyMapNotes(record: any): V5BodyServiceNote[] {
  const profile = asRecord(record?.profile);
  const reported = asRecord(profile.customer_reported);
  return (Array.isArray(reported.body_service_notes) ? reported.body_service_notes : []).flatMap((value) => {
    const note = asRecord(value);
    if (typeof note.region !== 'string' || typeof note.side !== 'string' || typeof note.context !== 'string' || typeof note.current_state !== 'string' || typeof note.session_handling !== 'string') return [];
    return [{
      region: note.region as V5BodyServiceNote['region'],
      side: note.side as V5BodyServiceNote['side'],
      context: note.context as V5BodyServiceNote['context'],
      currentState: note.current_state as V5BodyServiceNote['currentState'],
      sessionHandling: note.session_handling as V5BodyServiceNote['sessionHandling'],
      reconfirmNextVisit: note.reconfirm_next_visit === true,
    }];
  });
}

function Choices({ value, onChange, options, multiple = false, maxSelections }: {
  value?: string | string[]; onChange?: (value: any) => void;
  options: ReadonlyArray<{ value: string; label: string }>; multiple?: boolean; maxSelections?: number;
}) {
  return <Space wrap size={[8, 8]}>{options.map(option => {
    const selected = multiple ? Array.isArray(value) && value.includes(option.value) : value === option.value;
    const selectionLimitReached = multiple && !selected && maxSelections !== undefined && Array.isArray(value) && value.length >= maxSelections;
    return <Button key={option.value} size="large" type={selected ? 'primary' : 'default'} aria-pressed={selected}
      disabled={selectionLimitReached}
      onClick={() => onChange?.(multiple
        ? (selected ? (value as string[]).filter(item => item !== option.value) : [...(Array.isArray(value) ? value : []), option.value])
        : selected ? undefined : option.value)}>{option.label}</Button>;
  })}</Space>;
}

function serviceContext(items: any[]) {
  const names = items.map((item) => String(item?.name || '')).join(' ');
  const footCare = /泡脚|草本泡|足护|足部精修/.test(names);
  const bodyWork = /推拿|SPA|局部调理|功夫调理/.test(names);
  const adjustments = SERVICE_REFERENCE_OPTIONS.adjustments.filter((item) =>
    item.value === 'pace_slower' || item.value === 'end_early'
    || (bodyWork && ['pressure_lighter', 'pressure_stronger', 'focus_area', 'avoid_area'].includes(item.value))
    || (footCare && ['temperature_lower', 'temperature_higher'].includes(item.value))
  );
  return { footCare, bodyWork, adjustments };
}

export default function LegacyTechnicianProfileSheet({ task, onClose, onSaved }: { task: any; onClose: () => void; onSaved: () => void }) {
  const [form] = Form.useForm<CorrectionFormValues>();
  const values = Form.useWatch([], form) as CorrectionFormValues | undefined;
  const { message, modal } = App.useApp();
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const [confirmation, setConfirmation] = useState(false);
  const [bodyNoteOpen, setBodyNoteOpen] = useState(false);
  const [bodyMapNotes, setBodyMapNotes] = useState<V5BodyServiceNote[]>([]);
  const idempotencyKey = useRef(crypto.randomUUID());
  const lastPayloadSignature = useRef<string | null>(null);
  const lastValues = useRef<CorrectionFormValues | null>(null);
  const correction = task?.record?.schema_version === 5 ? task.record : null;
  const taskKey = `${task?.selection_session_id || ''}:${correction?.id || 'new'}`;

  useEffect(() => {
    form.resetFields();
    if (correction) form.setFieldsValue(correctionFormValues(correction));
    idempotencyKey.current = crypto.randomUUID();
    lastPayloadSignature.current = null;
    lastValues.current = null;
    setSaveFailed(false);
    setConfirmation(Boolean(correction?.customer_confirmed));
    setBodyMapNotes(correction ? correctionBodyMapNotes(correction) : []);
    setBodyNoteOpen(false);
  }, [form, taskKey]);

  const hasInput = Boolean(values && (hasServiceReferenceInput(values) || values.serviceNote?.trim()) || bodyMapNotes.length);
  const requestClose = () => {
    if (savingRef.current) return;
    if (!hasInput) { onClose(); return; }
    modal.confirm({ title: '笔记还没有保存', content: '返回后可以继续填写；放弃将清除本次未保存的内容。', okText: '继续填写', cancelText: '放弃内容', onCancel: onClose, maskClosable: false, closable: false });
  };
  const save = async (input: CorrectionFormValues) => {
    const customerId = task?.customer?.id ?? task?.user_id;
    if (!customerId || !task?.selection_session_id || savingRef.current) return;
    const { correctionReason, ...serviceInput } = input;
    if (!hasServiceReferenceInput(serviceInput) && !serviceInput.serviceNote?.trim() && !serviceInput.bodyMapNotes?.length && !serviceInput.recordingOutcome) return;
    if (correction && !correctionReason?.trim()) {
      message.error('请说明本次更正原因');
      return;
    }
    const payload = {
      ...buildServiceReferenceV5Payload(customerId, task.selection_session_id, serviceInput),
      ...(correction ? { correction_of_id: correction.id, correction_reason: correctionReason!.trim() } : {}),
    };
    const payloadSignature = JSON.stringify(payload);
    if (lastPayloadSignature.current !== null && lastPayloadSignature.current !== payloadSignature) idempotencyKey.current = crypto.randomUUID();
    lastPayloadSignature.current = payloadSignature;
    lastValues.current = input;
    savingRef.current = true;
    setSaving(true);
    setSaveFailed(false);
    try {
      await createCustomerProfileRecord(payload, idempotencyKey.current);
      message.success(correction ? '更正已保存，原记录已保留' : input.recordingOutcome ? '已记录：本次无补充' : '服务快记已保存');
      onSaved();
    } catch {
      setSaveFailed(true);
      message.error('未保存成功，内容已保留；请检查网络或填写内容后重试');
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const saveForm = (input: CorrectionFormValues) => void save({ ...input, bodyMapNotes, customerConfirmed: confirmation === true });
  const summary = (task?.items || []).map(technicianOrderItemLabel).filter(Boolean).join('、');
  const position = task?.room_name || task?.room_code || task?.position_name || '当前服务位';
  const context = serviceContext(task?.items || []);
  return <Drawer title={correction ? '更正本次服务交接' : '服务交接'} placement="bottom" height="94dvh" open={!!task}
    onClose={requestClose} maskClosable={false} keyboard={!saving}
    className="technician-profile-sheet technician-notebook" footer={<div className="technician-profile-sheet-actions">
      {!correction && <Button size="large" disabled={saving || hasInput} onClick={() => void save({ recordingOutcome: 'no_additional_notes', customerConfirmed: false })}>本次无补充</Button>}
      <Button type="primary" block size="large" loading={saving} disabled={saving || (!hasInput && !saveFailed)}
        onClick={() => saveFailed && lastValues.current ? void save(lastValues.current) : form.submit()}>{saveFailed ? '重试保存' : '保存快记'}</Button>
    </div>}>
    <Typography.Paragraph type="secondary">{position} · {summary || '本次服务'}</Typography.Paragraph>
    <Form form={form} layout="vertical" disabled={saving} onFinish={saveForm}
      onValuesChange={() => setSaveFailed(false)} initialValues={{ focusAreas: [], avoidAreas: [], serviceAdjustments: [] }}>
      <section className="notebook-preferences">
        <h2>下次怎样服务更合适？</h2><p>只记下次会改变服务动作的情况，没有可以留空。</p>
        <Form.Item name="communicationPreference" label="沟通"><Choices options={SERVICE_REFERENCE_OPTIONS.communication.filter(item => item.value !== 'explain_before_action')} /></Form.Item>
        {context.bodyWork && <><Form.Item name="forcePreference" label="力度"><Choices options={SERVICE_REFERENCE_OPTIONS.force} /></Form.Item>
          <Form.Item name="focusAreas" label="重点照顾"><Choices multiple maxSelections={3} options={SERVICE_REFERENCE_OPTIONS.focusAreas} /></Form.Item>
          <Form.Item name="avoidAreas" label="需要避开"><Choices multiple maxSelections={3} options={SERVICE_REFERENCE_OPTIONS.avoidAreas} /></Form.Item></>}
        {context.footCare && <Form.Item name="temperaturePreference" label="水温"><Choices options={SERVICE_REFERENCE_OPTIONS.temperature} /></Form.Item>}
      </section>
      <section className="notebook-followup">
        <h2>本次做了什么调整？</h2><p>选实际发生的动作，最多三项。</p>
        <Form.Item name="serviceAdjustments" label="本次调整"><Choices multiple maxSelections={3} options={context.adjustments} /></Form.Item>
      </section>
      <section className="notebook-followup">
        <h3>本次反馈与下次安排</h3>
        <Form.Item name="serviceFeedback" label="顾客反馈"><Choices options={SERVICE_REFERENCE_OPTIONS.feedback} /></Form.Item>
        <Form.Item name="nextVisitPlan" label="下次服务"><Choices options={SERVICE_REFERENCE_OPTIONS.nextVisit} /></Form.Item>
        <Button block size="large" disabled={saving} onClick={() => setBodyNoteOpen(true)}>{bodyMapNotes.length ? '查看 ' + bodyMapNotes.length + ' 条身体补充' : '记录身体情况（按需）'}</Button>
        <Checkbox checked={confirmation} disabled={saving} onChange={event => { setConfirmation(event.target.checked); setSaveFailed(false); }} style={{ marginTop: 16 }}>已向顾客复述并确认</Checkbox>
        <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>未确认也可保存；只有确认过的点选内容才供下次服务参考。</Typography.Paragraph>
      </section>
      <section className="notebook-writing">
        <h3>仅自己可见的补充</h3><p>只在确有必要时写，不会展示给下一位技师或管理端。</p>
        <Form.Item name="serviceNote" label="本次笔记">
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} maxLength={200} showCount placeholder="选填，仅记录本次服务中需要自己回看的内容。" />
        </Form.Item>
      </section>
      {correction && <section className="notebook-followup">
        <h3>更正说明</h3><p>说明这次改了什么；原记录会保留。</p>
        <Form.Item name="correctionReason" rules={[{ required: true, whitespace: true, message: '请说明本次更正原因' }]}>
          <Input maxLength={256} showCount placeholder="例如：补上当时漏记的力度调整" />
        </Form.Item>
      </section>}
    </Form>
    <BodyMapNoteDrawer open={bodyNoteOpen && !!task} value={bodyMapNotes}
      onChange={notes => { setBodyMapNotes(notes); setSaveFailed(false); }} onClose={() => setBodyNoteOpen(false)} context={position + ' · 顾客'} />
  </Drawer>;
}
