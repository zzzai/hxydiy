import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Checkbox, Drawer, Input, Spin } from 'antd';
import { createCustomerProfileRecord, getProjectRecordOptions } from '../api';
import {
  buildHandoffPayload,
  handoffPreview,
  hasHandoffContent,
  makeHandoff,
  type BodyRegion,
  type NextAction,
  type ServiceHandoff,
  type SessionChange,
} from './serviceHandoffRecord';
import './service-handoff.css';

type Props = { task: any; onClose: () => void; onSaved: () => void };
type Option = { value: string; label: string };

export default function ServiceHandoffSheet({ task, onClose, onSaved }: Props) {
  const initial = useRef<ServiceHandoff>(task.record?.schema_version === 7 ? task.record.profile : makeHandoff());
  const [record, setRecord] = useState<ServiceHandoff>(initial.current);
  const [confirmed, setConfirmed] = useState(Boolean(task.record?.customer_confirmed));
  const [options, setOptions] = useState<Record<string, Option[]>>();
  const [loadingError, setLoadingError] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  const busy = useRef(false);
  const saved = useRef(false);
  const signature = useRef('');
  const key = useRef(crypto.randomUUID());
  const { modal, message } = App.useApp();
  const content = hasHandoffContent(record);
  const dirty = JSON.stringify(record) !== JSON.stringify(initial.current) || confirmed !== Boolean(task.record?.customer_confirmed);
  const preview = handoffPreview(record);

  useEffect(() => {
    let active = true;
    setLoadingError(false);
    getProjectRecordOptions(7).then(({ data }) => {
      if (data?.taxonomy_version !== 'service_handoff_v1') throw Error('Version mismatch');
      if (active) setOptions(data.groups);
    }).catch(() => { if (active) setLoadingError(true); });
    return () => { active = false; };
  }, [reload]);

  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirty && !saved.current) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [dirty]);

  const change = (patch: Partial<ServiceHandoff>) => {
    setRecord((value) => ({ ...value, ...patch, recording_outcome: undefined }));
    setError('');
  };
  const toggle = <T extends string>(values: T[], value: T, max = 3) => values.includes(value) ? values.filter((item) => item !== value) : values.length < max ? [...values, value] : values;
  const choices = (group: string, value: string | undefined, onChange: (value: string | undefined) => void) => (
    <div className="handoff-choices">{(options?.[group] || []).map((option) => (
      <button type="button" key={option.value} aria-pressed={value === option.value} onClick={() => onChange(value === option.value ? undefined : option.value)}>{option.label}</button>
    ))}</div>
  );
  const close = () => {
    if (busy.current) return;
    if (!dirty) { onClose(); return; }
    modal.confirm({ title: '记录还没有保存', content: '继续填写，或放弃本次未保存的修改。', okText: '继续填写', cancelText: '放弃修改', onCancel: onClose, maskClosable: false, closable: false });
  };
  const submit = async (empty = false) => {
    if (busy.current) return;
    let payload;
    try {
      const value = empty ? { ...makeHandoff(), recording_outcome: 'no_additional_notes' as const } : record;
      payload = buildHandoffPayload(task.customer?.id || task.user_id, task.selection_session_id, value, empty ? false : confirmed, task.record?.id);
    } catch (reason) { setError((reason as Error).message); return; }
    const next = JSON.stringify(payload);
    if (signature.current && signature.current !== next) key.current = crypto.randomUUID();
    signature.current = next;
    busy.current = true; setSaving(true); setError('');
    try {
      await createCustomerProfileRecord(payload, key.current);
      saved.current = true;
      message.success('已留给下次服务');
      onSaved();
    } catch (reason: any) {
      const status = reason?.response?.status;
      setError(status === 409 ? '记录状态已变化或已有新版本，内容已保留。' : status === 403 ? '当前账号无权记录这次服务，内容已保留。' : status === 422 ? '内容未通过校验，请检查后重试。' : '保存失败，内容已保留，请重试。');
    } finally { busy.current = false; setSaving(false); }
  };

  const selectedRegion = (region: BodyRegion) => record.body_focus.find((item) => item.region === region);
  const toggleRegion = (region: BodyRegion) => {
    const current = selectedRegion(region);
    if (current) change({ body_focus: record.body_focus.filter((item) => item.region !== region) });
    else if (record.body_focus.length < 3) change({ body_focus: [...record.body_focus, { region }] });
  };
  const updateAction = (region: BodyRegion, next_action: NextAction | undefined) => change({
    body_focus: record.body_focus.map((item) => item.region === region ? { ...item, next_action } : item),
  });

  return <Drawer title={task.record ? '更正本次记录' : '给下次服务留句话'} open placement="bottom" height="96dvh" onClose={close} maskClosable={false} keyboard={!saving} className="service-handoff-sheet"
    footer={<div className="handoff-actions"><Button size="large" disabled={saving || content || confirmed || !options} onClick={() => void submit(true)}>本次没有新情况</Button><Button type="primary" size="large" loading={saving} disabled={saving || !options || !content || (!dirty && !!task.record)} onClick={() => void submit()}>保存，留给下次</Button></div>}>
    <div className="handoff-content">
      <header><p>{task.room_name || task.position_name || '本次服务'} · {(task.items || []).map((item: any) => item.name).join('、')}</p><h1>下次接待，一眼就能用</h1></header>
      <div className={`handoff-preview ${preview.length ? '' : 'is-empty'}`}><span>交接预览</span><p>{preview.length ? preview.join('；') : '点选后，这里会自动生成给下次服务的提醒。'}</p></div>
      {loadingError ? <Alert type="error" message="记录选项加载失败" action={<Button onClick={() => setReload((value) => value + 1)}>重试</Button>} /> : !options ? <Spin /> : <fieldset disabled={saving}>
        <section><div className="handoff-heading"><span>01</span><div><h2>顾客这次想怎么待着？</h2><p>只记明确表现，不必猜。</p></div></div>{choices('communication', record.communication, (value) => change({ communication: value as ServiceHandoff['communication'] }))}</section>
        <section><div className="handoff-heading"><span>02</span><div><h2>下次服务，哪里要特别留意？</h2><p>最多三处；选中部位后，再选怎么做。</p></div></div>
          <div className="handoff-choices">{options.body_region.map((option) => <button type="button" key={option.value} aria-pressed={Boolean(selectedRegion(option.value as BodyRegion))} onClick={() => toggleRegion(option.value as BodyRegion)}>{option.label}</button>)}</div>
          {record.body_focus.map((item) => <div className="handoff-body-action" key={item.region}><strong>{options.body_region.find((option) => option.value === item.region)?.label}</strong>{choices('next_action', item.next_action, (value) => updateAction(item.region, value as NextAction | undefined))}</div>)}
        </section>
        <section><div className="handoff-heading"><span>03</span><div><h2>这次服务做过哪些调整？</h2><p>只选真正发生过的变化。</p></div></div><div className="handoff-choices">{options.session_change.map((option) => <button type="button" key={option.value} aria-pressed={record.session_changes.includes(option.value as SessionChange)} onClick={() => change({ session_changes: toggle(record.session_changes, option.value as SessionChange) })}>{option.label}</button>)}</div></section>
        <details><summary>补充基本信息（选填）</summary><div className="handoff-detail"><h3>年龄段</h3>{choices('age_band', record.basic_info?.age_band, (value) => change({ basic_info: { ...record.basic_info, age_band: value as any } }))}<h3>性别</h3>{choices('gender', record.basic_info?.gender, (value) => change({ basic_info: { ...record.basic_info, gender: value as any } }))}</div></details>
        <details><summary>补充一句（仅本人可见）</summary><div className="handoff-detail"><Input.TextArea maxLength={200} value={record.private_note} autoSize={{ minRows: 3, maxRows: 7 }} placeholder="例如：下次先问右肩今天的感受" onChange={(event) => change({ private_note: event.target.value })} /><p>不会展示给其他技师或进入管理端交接摘要。</p></div></details>
        <section className="handoff-confirm"><Checkbox disabled={!content} checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}>我已向顾客确认以上点选内容</Checkbox><p>未确认也能保存，但不会作为其他技师的确定事实。</p></section>
      </fieldset>}
      {error && <Alert role="alert" type="error" showIcon message={error} />}
    </div>
  </Drawer>;
}
