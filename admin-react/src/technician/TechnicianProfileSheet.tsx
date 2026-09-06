import { useEffect, useRef, useState } from 'react';
import { App, Button, Collapse, Drawer, Form, Input, List, Modal, Radio, Tag, Typography } from 'antd';
import { createCustomerProfileRecord } from '../api';
import { technicianOrderItemLabel } from './technicianMobile';
import { SERVICE_REFERENCE_OPTIONS, buildServiceReferenceV3Payload, hasServiceReferenceInput, type ServiceReferenceInput } from './serviceReference';

const MORE_REFERENCE_OPTIONS = {
  ageBand: [{ label: '18–24 岁', value: '18_24' }, { label: '25–34 岁', value: '25_34' }, { label: '35–44 岁', value: '35_44' }, { label: '45–54 岁', value: '45_54' }, { label: '55–64 岁', value: '55_64' }, { label: '65 岁以上', value: '65_plus' }],
  build: [{ label: '偏瘦', value: 'slim' }, { label: '匀称', value: 'balanced' }, { label: '偏壮', value: 'sturdy' }],
  heightBand: [{ label: '偏矮', value: 'shorter' }, { label: '适中', value: 'average' }, { label: '偏高', value: 'taller' }],
  occupationContexts: [{ label: '久坐办公', value: 'desk_work' }, { label: '久站服务', value: 'standing_work' }, { label: '经常驾驶', value: 'frequent_driving' }, { label: '体力劳动', value: 'physical_labor' }, { label: '照护家庭', value: 'family_care' }, { label: '自由职业', value: 'freelance' }, { label: '退休', value: 'retired' }, { label: '其他', value: 'other' }],
  sleepQuality: [{ label: '良好', value: 'good' }, { label: '一般', value: 'average' }, { label: '较差', value: 'poor' }],
  serviceContexts: [{ label: '长期身体情况', value: 'long_term_condition' }, { label: '近期不适或恢复', value: 'recent_discomfort_recovery' }, { label: '皮肤敏感或接触偏好', value: 'skin_sensitivity' }, { label: '提到正在用药', value: 'medication_mentioned' }, { label: '孕期或产后阶段', value: 'pregnancy_postpartum' }, { label: '其他需再次确认', value: 'other_reconfirm' }],
  relaxation: [{ label: '较快放松', value: 'quick' }, { label: '逐渐放松', value: 'gradual' }, { label: '始终较紧张', value: 'tense' }],
  decisionPriorities: [{ label: '价格', value: 'price' }, { label: '品质', value: 'quality' }, { label: '环境', value: 'environment' }, { label: '效率', value: 'efficiency' }, { label: '固定技师', value: 'fixed_technician' }, { label: '固定时段', value: 'fixed_time' }],
  budgetPreference: [{ label: '实惠优先', value: 'value' }, { label: '平衡', value: 'balanced' }, { label: '体验优先', value: 'experience' }, { label: '未表达', value: 'unexpressed' }],
} as const;

function hasV3Input(values: ServiceReferenceInput) {
  return Boolean(values.personalContext?.ageBand || values.personalContext?.build || values.personalContext?.heightBand
    || values.workLifestyle?.occupationContexts?.length || values.workLifestyle?.sleepQuality
    || values.serviceRelatedContext?.contexts?.length || values.serviceRelatedContext?.quote?.trim()
    || values.sessionResponse?.relaxation || values.communicationConsumption?.decisionPriorities?.length
    || values.communicationConsumption?.budgetPreference);
}

const selectedLabels = (values: string[] | undefined, options: ReadonlyArray<{ label: string; value: string }>) =>
  (values || []).map((value) => options.find((option) => option.value === value)?.label).filter(Boolean).join('、');
const selectedLabel = (value: string | undefined, options: ReadonlyArray<{ label: string; value: string }>) =>
  options.find((option) => option.value === value)?.label;

function safeDraftSummary(values: ServiceReferenceInput): string[] {
  const lines = [
    selectedLabels(values.focusAreas, SERVICE_REFERENCE_OPTIONS.focusAreas) && `本次重点：${selectedLabels(values.focusAreas, SERVICE_REFERENCE_OPTIONS.focusAreas)}`,
    selectedLabels(values.avoidAreas, SERVICE_REFERENCE_OPTIONS.avoidAreas) && `避开或谨慎：${selectedLabels(values.avoidAreas, SERVICE_REFERENCE_OPTIONS.avoidAreas)}`,
    selectedLabel(values.forcePreference, SERVICE_REFERENCE_OPTIONS.force) && `力度偏好：${selectedLabel(values.forcePreference, SERVICE_REFERENCE_OPTIONS.force)}`,
    selectedLabel(values.temperaturePreference, SERVICE_REFERENCE_OPTIONS.temperature) && `温度偏好：${selectedLabel(values.temperaturePreference, SERVICE_REFERENCE_OPTIONS.temperature)}`,
    selectedLabel(values.serviceFeedback, SERVICE_REFERENCE_OPTIONS.feedback) && `服务反馈：${selectedLabel(values.serviceFeedback, SERVICE_REFERENCE_OPTIONS.feedback)}`,
    selectedLabel(values.nextVisitPlan, SERVICE_REFERENCE_OPTIONS.nextVisit) && `下次建议：${selectedLabel(values.nextVisitPlan, SERVICE_REFERENCE_OPTIONS.nextVisit)}`,
    selectedLabel(values.personalContext?.ageBand, MORE_REFERENCE_OPTIONS.ageBand) && `年龄段：${selectedLabel(values.personalContext?.ageBand, MORE_REFERENCE_OPTIONS.ageBand)}`,
    selectedLabel(values.personalContext?.build, MORE_REFERENCE_OPTIONS.build) && `体型：${selectedLabel(values.personalContext?.build, MORE_REFERENCE_OPTIONS.build)}`,
    selectedLabel(values.personalContext?.heightBand, MORE_REFERENCE_OPTIONS.heightBand) && `身高印象：${selectedLabel(values.personalContext?.heightBand, MORE_REFERENCE_OPTIONS.heightBand)}`,
    selectedLabels(values.workLifestyle?.occupationContexts, MORE_REFERENCE_OPTIONS.occupationContexts) && `职业场景：${selectedLabels(values.workLifestyle?.occupationContexts, MORE_REFERENCE_OPTIONS.occupationContexts)}`,
    selectedLabel(values.workLifestyle?.sleepQuality, MORE_REFERENCE_OPTIONS.sleepQuality) && `睡眠自述：${selectedLabel(values.workLifestyle?.sleepQuality, MORE_REFERENCE_OPTIONS.sleepQuality)}`,
    selectedLabels(values.serviceRelatedContext?.contexts, MORE_REFERENCE_OPTIONS.serviceContexts) && `相关情况：${selectedLabels(values.serviceRelatedContext?.contexts, MORE_REFERENCE_OPTIONS.serviceContexts)}`,
    selectedLabel(values.sessionResponse?.relaxation, MORE_REFERENCE_OPTIONS.relaxation) && `放松过程：${selectedLabel(values.sessionResponse?.relaxation, MORE_REFERENCE_OPTIONS.relaxation)}`,
    selectedLabels(values.communicationConsumption?.decisionPriorities, MORE_REFERENCE_OPTIONS.decisionPriorities) && `决策关注：${selectedLabels(values.communicationConsumption?.decisionPriorities, MORE_REFERENCE_OPTIONS.decisionPriorities)}`,
    selectedLabel(values.communicationConsumption?.budgetPreference, MORE_REFERENCE_OPTIONS.budgetPreference) && `预算倾向：${selectedLabel(values.communicationConsumption?.budgetPreference, MORE_REFERENCE_OPTIONS.budgetPreference)}`,
    values.serviceRelatedContext?.quote?.trim() && `顾客原话：${values.serviceRelatedContext.quote.trim()}`,
  ];
  return lines.filter((line): line is string => Boolean(line));
}

function makeIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() || `profile-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function CheckableField({ value = [], onChange, options, maxSelected, onLimit }: { value?: string[]; onChange?: (value: string[]) => void; options: ReadonlyArray<{ label: string; value: string }>; maxSelected?: number; onLimit?: () => void }) {
  return <div className="technician-tag-list">{options.map((option) => {
    const checked = value.includes(option.value);
    return <Tag.CheckableTag key={option.value} checked={checked} onChange={(next) => {
      if (next && maxSelected !== undefined && value.length >= maxSelected) { onLimit?.(); return; }
      onChange?.(next ? [...value, option.value] : value.filter((item) => item !== option.value));
    }}>{option.label}</Tag.CheckableTag>;
  })}</div>;
}

export default function TechnicianProfileSheet({ task, onClose, onSaved }: { task: any; onClose: () => void; onSaved: () => void }) {
  const [form] = Form.useForm<ServiceReferenceInput>();
  const { message } = App.useApp();
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const [draft, setDraft] = useState<ServiceReferenceInput | null>(null);
  const [confirmation, setConfirmation] = useState<boolean | undefined>();
  const idempotencyKey = useRef(makeIdempotencyKey());
  const lastPayloadSignature = useRef<string | null>(null);

  useEffect(() => {
    form.resetFields();
    idempotencyKey.current = makeIdempotencyKey();
    lastPayloadSignature.current = null;
    setSaveFailed(false);
    setDraft(null);
    setConfirmation(undefined);
  }, [form, task]);

  const save = async (values: ServiceReferenceInput) => {
    const customerId = task?.customer?.id ?? task?.user_id;
    if (!customerId || !task?.selection_session_id || saving) return;
    if (!hasServiceReferenceInput(values) && !hasV3Input(values)) {
      message.warning('请至少选择或填写一项服务参考');
      return;
    }
    setSaving(true);
    setSaveFailed(false);
    const confirmedValues = { ...values, customerConfirmed: confirmation === true };
    const payload = buildServiceReferenceV3Payload(customerId, task.selection_session_id, confirmedValues);
    const payloadSignature = JSON.stringify(payload);
    if (lastPayloadSignature.current !== null && lastPayloadSignature.current !== payloadSignature) {
      idempotencyKey.current = makeIdempotencyKey();
    }
    lastPayloadSignature.current = payloadSignature;
    try {
      await createCustomerProfileRecord(payload, idempotencyKey.current);
      message.success('服务参考已记录');
      setDraft(null);
      onSaved();
    } catch {
      setSaveFailed(true);
      message.error('保存未成功，请按提示检查内容后重试');
    } finally {
      setSaving(false);
    }
  };

  const summary = (task?.items || []).map(technicianOrderItemLabel).filter(Boolean).join('、') || '顾客暂未填写项目';
  const position = task?.room_name || task?.room_code || task?.position_name || '当前服务位';
  const openSummary = (values: ServiceReferenceInput) => {
    if (!hasServiceReferenceInput(values) && !hasV3Input(values)) {
      message.warning('请至少选择或填写一项服务参考');
      return;
    }
    setConfirmation(undefined);
    setDraft(values);
  };

  return <Drawer title="本次服务参考" placement="bottom" height="min(94vh, 820px)" open={!!task} onClose={saving ? undefined : onClose} className="technician-profile-sheet" footer={<div className="technician-profile-sheet-actions">
    <Button block size="large" onClick={onClose} disabled={saving}>暂不记录</Button>
    <Button type="primary" block size="large" onClick={() => form.submit()} loading={saving} disabled={saving}>{saveFailed ? '重试保存' : '保存服务参考'}</Button>
  </div>}>
    <div className="technician-profile-context">
      <div><Typography.Text strong>{position}</Typography.Text><Tag color="blue">已完成</Tag></div>
      <Typography.Text type="secondary">{task?.customer?.nickname || '顾客'} · {summary}</Typography.Text>
      <Typography.Paragraph type="secondary">点选即可，建议当面复述确认；仅作到店服务参考。</Typography.Paragraph>
    </div>
    <Form form={form} layout="vertical" onFinish={openSummary} initialValues={{ focusAreas: [], avoidAreas: [], workLifestyle: { occupationContexts: [] }, serviceRelatedContext: { contexts: [] } }}>
      <Form.Item name="focusAreas" label="本次重点"><CheckableField options={SERVICE_REFERENCE_OPTIONS.focusAreas} /></Form.Item>
      <Form.Item name="avoidAreas" label="避开或谨慎"><CheckableField options={SERVICE_REFERENCE_OPTIONS.avoidAreas} /></Form.Item>
      <Form.Item name="forcePreference" label="力度偏好"><Radio.Group optionType="button" buttonStyle="solid" options={SERVICE_REFERENCE_OPTIONS.force} /></Form.Item>
      <Form.Item name="temperaturePreference" label="温度偏好"><Radio.Group optionType="button" buttonStyle="solid" options={SERVICE_REFERENCE_OPTIONS.temperature} /></Form.Item>
      <Form.Item name="serviceFeedback" label="服务反馈"><Radio.Group optionType="button" buttonStyle="solid" options={SERVICE_REFERENCE_OPTIONS.feedback} /></Form.Item>
      <Form.Item name="nextVisitPlan" label="下次建议"><Radio.Group optionType="button" buttonStyle="solid" options={SERVICE_REFERENCE_OPTIONS.nextVisit} /></Form.Item>
      <Collapse ghost items={[{ key: 'more', label: '更多服务记忆', children: <>
        <Typography.Paragraph type="secondary">按需补充；未选择的维度不会写入。身体、健康或用药相关情况仅记录顾客自述，服务前请再次确认。</Typography.Paragraph>
        <Form.Item name={['personalContext', 'ageBand']} label="年龄段"><Radio.Group optionType="button" buttonStyle="solid" options={[...MORE_REFERENCE_OPTIONS.ageBand]} /></Form.Item>
        <Form.Item name={['personalContext', 'build']} label="体型"><Radio.Group optionType="button" buttonStyle="solid" options={[...MORE_REFERENCE_OPTIONS.build]} /></Form.Item>
        <Form.Item name={['personalContext', 'heightBand']} label="身高区间"><Radio.Group optionType="button" buttonStyle="solid" options={[...MORE_REFERENCE_OPTIONS.heightBand]} /></Form.Item>
        <Form.Item name={['workLifestyle', 'occupationContexts']} label="工作与生活场景" extra="最多选择 2 项"><CheckableField options={MORE_REFERENCE_OPTIONS.occupationContexts} maxSelected={2} onLimit={() => message.warning('工作与生活场景最多选择 2 项')} /></Form.Item>
        <Form.Item name={['workLifestyle', 'sleepQuality']} label="睡眠自述"><Radio.Group optionType="button" buttonStyle="solid" options={[...MORE_REFERENCE_OPTIONS.sleepQuality]} /></Form.Item>
        <Form.Item name={['serviceRelatedContext', 'contexts']} label="服务相关情况" extra="最多选择 1 项"><CheckableField options={MORE_REFERENCE_OPTIONS.serviceContexts} maxSelected={1} onLimit={() => message.warning('服务相关情况最多选择 1 项')} /></Form.Item>
        <Form.Item name={['serviceRelatedContext', 'quote']} label="相关情况原话"><Input.TextArea rows={2} maxLength={100} showCount placeholder="顾客自述，服务前请再次确认" /></Form.Item>
        <Form.Item name={['sessionResponse', 'relaxation']} label="本次放松反应"><Radio.Group optionType="button" buttonStyle="solid" options={[...MORE_REFERENCE_OPTIONS.relaxation]} /></Form.Item>
        <Form.Item name={['communicationConsumption', 'decisionPriorities']} label="决策关注"><CheckableField options={MORE_REFERENCE_OPTIONS.decisionPriorities} /></Form.Item>
        <Form.Item name={['communicationConsumption', 'budgetPreference']} label="预算倾向"><Radio.Group optionType="button" buttonStyle="solid" options={[...MORE_REFERENCE_OPTIONS.budgetPreference]} /></Form.Item>
        <Typography.Paragraph type="secondary">不询问或保存具体收入、资产或负债；预算偏好不得用于差别定价。</Typography.Paragraph>
      </> }]} />
    </Form>
    <Modal title="保存前确认摘要" open={!!draft} confirmLoading={saving} okText={confirmation === true ? '保存为长期摘要' : '保存本次观察'} cancelText="返回修改" okButtonProps={{ disabled: confirmation === undefined }} onCancel={() => !saving && setDraft(null)} onOk={() => draft && void save(draft)}>
      <Typography.Paragraph>请向顾客复述本次记录。只有顾客确认后，内容才会进入下次可见的长期摘要。</Typography.Paragraph>
      <Typography.Text strong>待保存摘要</Typography.Text>
      <List size="small" dataSource={draft ? safeDraftSummary(draft) : []} renderItem={(line) => <List.Item>{line}</List.Item>} />
      <Form.Item label="已向顾客复述并确认" required>
        <Radio.Group value={confirmation} onChange={(event) => setConfirmation(event.target.value)} options={[{ label: '顾客已确认', value: true }, { label: '未确认，仅保存为本次观察', value: false }]} />
      </Form.Item>
      <Typography.Text type="secondary">健康、用药等内容仅来自顾客自述，服务前请再次确认。</Typography.Text>
    </Modal>
  </Drawer>;
}
