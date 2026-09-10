import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Checkbox, Drawer, Input, Spin } from 'antd';
import { createCustomerProfileRecord, getProjectRecordOptions } from '../api';
import LegacyTechnicianProfileSheet from './LegacyTechnicianProfileSheet';
import { buildRecordPayload, hasRecordContent, makeRecord, type ProjectRecord } from './projectServiceRecord';
import './project-service-record.css';

type Props = {task: any; onClose: () => void; onSaved: () => void};
type Option = {value: string; label: string};
export default function TechnicianProfileSheet(props: Props) {
  if (!props.task) return null;
  return makeRecord(props.task.items || []).template === 'herbal_signature_v1' || props.task.record?.schema_version === 6
    ? <ProjectRecordSheet key={`${props.task.selection_session_id}:${props.task.record?.id || 'new'}`} {...props} />
    : <LegacyTechnicianProfileSheet {...props} />;
}

function ProjectRecordSheet({task, onClose, onSaved}: Props) {
  const initial = useRef<ProjectRecord>(task.record?.profile || makeRecord(task.items || []));
  const [record, setRecord] = useState<ProjectRecord>(initial.current);
  const [confirmed, setConfirmed] = useState(false);
  const [options, setOptions] = useState<Record<string, Option[]>>();
  const [loadingError, setLoadingError] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  const saved = useRef(false);
  const signature = useRef('');
  const key = useRef(crypto.randomUUID());
  const {modal, message} = App.useApp();
  const [reload, setReload] = useState(0);
  const content = hasRecordContent(record);
  const dirty = JSON.stringify(record) !== JSON.stringify(initial.current) || confirmed;
  useEffect(() => {
    let active = true;
    setLoadingError(false);
    getProjectRecordOptions().then(result => {
      if (result.data?.taxonomy_version !== 'service_record_v1') throw Error('Version mismatch');
      if (active) setOptions(result.data.groups);
    }).catch(()=>{if(active)setLoadingError(true);});
    return ()=>{active=false;};
  }, [reload]);
  useEffect(()=>{
    const guard = (event: BeforeUnloadEvent)=>{if(dirty && !saved.current){event.preventDefault();event.returnValue='';}};
    window.addEventListener('beforeunload',guard);
    return ()=>window.removeEventListener('beforeunload',guard);
  },[dirty]);
  const change = (patch: Partial<ProjectRecord>) => {setRecord(value=>({...value,...patch,recording_outcome:undefined}));setError('');};
  const close = ()=>{
    if(busy.current)return;
    if(!dirty){onClose();return;}
    modal.confirm({title:'记录还没有保存',content:'继续填写，或放弃本次未保存的修改。',okText:'继续填写',cancelText:'放弃修改',onCancel:onClose,maskClosable:false,closable:false});
  };
  const submit = async (empty=false)=>{
    if(busy.current)return;
    let payload;
    try {
      const value = empty ? {...makeRecord(task.items || []),recording_outcome:'no_additional_notes' as const} : record;
      payload = buildRecordPayload(task.customer?.id || task.user_id,task.selection_session_id,value,empty?false:confirmed,task.record?.id);
    } catch(reason){setError((reason as Error).message);return;}
    const next = JSON.stringify(payload);
    if(signature.current && signature.current !== next)key.current=crypto.randomUUID();
    signature.current=next;busy.current=true;setSaving(true);setError('');
    try {
      await createCustomerProfileRecord(payload,key.current);
      saved.current=true;
      message.success('记录已保存，可在服务记录中回看');
      onSaved();
    } catch(reason: any) {
      const status = reason?.response?.status;
      setError(status===409?'记录状态已变化或已有新版本。内容已保留，请检查历史记录后重试。':status===403?'当前账号无权记录这次服务，内容已保留。':status===422?'内容未通过校验，请检查部位、重复条目和补充文字，不要填写诊断或治疗结论。':'保存失败，内容已保留，请重试。');
    } finally {busy.current=false;setSaving(false);}
  };
  const choices = (group: string, value: string | undefined, onChange: (value: string | undefined)=>void)=>
    <div className="project-record-choices">{(options?.[group] || []).map(option=><button type="button" key={option.value} aria-pressed={value===option.value} onClick={()=>onChange(value===option.value?undefined:option.value)}>{option.label}</button>)}</div>;
  const updateMassage = (index: number, patch: Record<string,string | undefined>)=>change({massage:record.massage?.map((item,i)=>i===index?{...item,...patch}:item)});
  return <Drawer title={task.record?'更正本次记录':'记录本次服务'} open placement="bottom" height="94dvh" onClose={close} maskClosable={false} keyboard={!saving} className="project-record-sheet"
    footer={<div className="project-record-actions"><Button size="large" disabled={saving || content || confirmed || !options} onClick={()=>void submit(true)}>本次没有新情况</Button><Button type="primary" size="large" aria-label={saving?'正在保存':'保存记录'} loading={saving} disabled={saving || !options || !content || (!dirty && !!task.record)} onClick={()=>void submit()}>保存记录</Button></div>}>
    <div className="project-record-content">
      <p className="project-record-context">{task.room_name || task.position_name || '本次服务'} · {(task.items || []).map((item:any)=>item.name).join('、')}</p>
      <p>只选顾客明确表达的情况，不必每项填写。</p>
      {loadingError?<Alert type="error" message="记录选项加载失败" action={<Button onClick={()=>setReload(value=>value+1)}>重试</Button>} />:!options?<Spin />:
      <fieldset disabled={saving}>
        {record.template==='herbal_signature_v1' && <>
          <section><h2>泡脚时，顾客对水温有要求吗？</h2>
            {choices('water_request',record.water?.request,value=>change({water:value?{request:value}:undefined}))}
            {record.water?.request && record.water.request!=='suitable' && <div className="project-record-adjustment"><h3>本次怎么处理？</h3>{choices('water_action',record.water?.action,value=>change({water:{...record.water,action:value}}))}<h3>调整后，顾客怎么说？</h3>{choices('water_feedback',record.water?.feedback,value=>change({water:{...record.water,feedback:value}}))}<p>没有明确反馈，可以不选。</p></div>}
          </section>
          <section><h2>按摩时，哪些地方需要调整？</h2>
            {(record.massage || []).map((item,index)=><div className="project-record-entry" key={index}>
              <div className="project-record-locations"><label>哪个部位？<select value={item.region} onChange={event=>updateMassage(index,{region:event.target.value})}><option value="">请选择</option>{options.region.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select></label><label>哪一侧？<select value={item.side} onChange={event=>updateMassage(index,{side:event.target.value})}>{options.side.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select></label></div>
              <h3>顾客有什么要求？</h3>{choices('massage_request',item.request,value=>updateMassage(index,{request:value}))}
              <h3>本次怎么处理？</h3>{choices('massage_action',item.action,value=>updateMassage(index,{action:value}))}
              <h3>顾客反馈</h3>{choices('massage_feedback',item.feedback,value=>updateMassage(index,{feedback:value}))}
              <button className="project-record-delete" type="button" onClick={()=>change({massage:record.massage?.filter((_,i)=>i!==index)})}>删除这条</button>
            </div>)}
            <button type="button" disabled={(record.massage?.length || 0)>=3} onClick={()=>change({massage:[...(record.massage || []),{region:'',side:'unspecified'}]})}>添加一处</button>
          </section>
          <section><h2>热敷时，有什么需要记录？</h2>{choices('heat',record.heat,value=>change({heat:value}))}
            <label className="project-record-text-label" htmlFor="project-heat-note">如有调整，补充本次处理和顾客反馈</label><Input.TextArea id="project-heat-note" disabled={saving} value={record.heat_note || ''} maxLength={200} autoSize={{minRows:2,maxRows:6}} onChange={event=>change({heat_note:event.target.value})} />
            <p>未做热敷可以跳过。不适须当场处理，记录不能代替处理。</p>
          </section>
        </>}
        <section><h2>顾客想聊天还是休息？</h2>{choices('communication',record.communication,value=>change({communication:value}))}</section>
        <section><h2><label htmlFor="project-service-note">还有其他需要记住的事吗？</label></h2><Input.TextArea id="project-service-note" disabled={saving} maxLength={200} value={record.service_note || ''} autoSize={{minRows:3,maxRows:8}} placeholder="选填，可使用键盘语音输入。" onChange={event=>change({service_note:event.target.value})} /><p>补充文字仅本人可见，不会作为其他技师的服务前参考。</p></section>
        <section><Checkbox disabled={saving || !content} checked={confirmed} onChange={event=>setConfirmed(event.target.checked)}>已向顾客复述以上点选内容，并得到确认</Checkbox><p>未确认也可保存；只有已确认的点选内容才作为下次服务参考。补充文字不对其他技师展示。</p></section>
      </fieldset>}
      {error && <Alert role="alert" type="error" showIcon message={error} />}
    </div>
  </Drawer>;
}
