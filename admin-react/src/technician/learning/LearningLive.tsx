import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { client, getStaff } from '../../api';
import { requestErrorMessage } from '../../requestError';
import { LearningEntry } from './LearningPage';
import DailyLearningPage from './DailyLearningPage';
import type { LearningActor, LearningAssignment, LearningCourse, LearningGateway } from './learningModel';
import { learningIdentity } from './learningModel';

type Snapshot = { actor: LearningActor; assignments: LearningAssignment[]; courses: LearningCourse[]; roster: Array<{id:number;name:string}>; assignableCourses: Array<{id:string;version:string}> };
function currentActor(): LearningActor | null {
  const staff = getStaff();
  return staff && typeof staff.id === 'number' && staff.id > 0 && staff.store_id && (staff.role === 'manager' || staff.role === 'technician') ? {id:staff.id,storeId:staff.store_id,role:staff.role as LearningActor['role'],name:staff.name || ''} : null;
}
function assertIdentity(expected: LearningActor) {
  const current = currentActor();
  if (!current || learningIdentity(current) !== learningIdentity(expected)) throw new Error('登录身份已变化，请重新进入学习');
}
function checkedSnapshot(data: Snapshot, expected: LearningActor): Snapshot {
  assertIdentity(expected);
  if (learningIdentity(data.actor) !== learningIdentity(expected)) throw new Error('学习身份不匹配，请重新登录');
  return data;
}
function learningError(failure: unknown): Error {
  const detail = (failure as {response?:{data?:{detail?:{code?:string}}}})?.response?.data?.detail;
  return Object.assign(new Error(requestErrorMessage(failure)), {code: detail?.code});
}
async function readSnapshot(expected: LearningActor): Promise<Snapshot> {
  assertIdentity(expected);
  try {
    const {data} = await client.get<Snapshot>('/staff-learning/bootstrap');
    return checkedSnapshot(data, expected);
  } catch (error) { throw new Error(requestErrorMessage(error)); }
}

export default function LearningLive({ entry = false }: {entry?:boolean}) {
  const navigate = useNavigate();
  const identity = currentActor();
  const identityKey = identity && learningIdentity(identity);
  const [data,setData] = useState<Snapshot|null>(null);
  const [disabled,setDisabled] = useState(false);
  const [error,setError] = useState('');
  const [reload,setReload] = useState(0);
  const [assigning,setAssigning] = useState(false);
  const [learner,setLearner] = useState('');
  const [courseKey,setCourseKey] = useState('');
  const [busy,setBusy] = useState(false);
  const [assigned,setAssigned] = useState(false);
  const saving = useRef(false);
  const pending = useRef<{payload:string;key:string}>();
  const alive = useRef(true);
  useEffect(()=>{
    alive.current=true; let active=true;
    setData(null);setError('');setDisabled(false);
    if (!identity) return;
    const expected=identity;
    void (async()=>{
      try {
        const status=await client.get<{enabled:boolean}>('/staff-learning/status');
        assertIdentity(expected);
        if (!active) return;
        if (!status.data.enabled) {setDisabled(true);return;}
        const snapshot=await readSnapshot(expected);
        if(active)setData(snapshot);
      } catch(failure) {if(active)setError(requestErrorMessage(failure));}
    })();
    return ()=>{active=false;alive.current=false;};
  },[identityKey,reload]);
  const gateway=useMemo<LearningGateway|null>(()=>!data ? null : {
    currentActor,
    list: async actor => (await readSnapshot(actor)).assignments,
    execute: async(actor,command)=>{
      assertIdentity(actor);
      const body={kind:command.kind,request_id:command.requestId,expected_revision:command.expectedRevision,
        ...(command.sectionId ? {section_id:command.sectionId}:{}),
        ...(command.answers ? {answers:command.answers}:{}),
        ...(command.note !== undefined ? {note:command.note}:{})};
      try {
        const response=await client.post<Snapshot>(`/staff-learning/assignments/${command.assignmentId}/actions`,body);
        return checkedSnapshot(response.data, actor).assignments;
      } catch(failure) {throw learningError(failure);}
    }
  },[data?.actor.id,data?.actor.storeId,data?.actor.role]);
  if (data && identityKey !== learningIdentity(data.actor)) return null;
  if (disabled) return entry ? null : <section className="learning-page"><button className="learning-back" onClick={()=>navigate(identity?.role==='manager'?'/store':'/today')}>返回工作台</button><p>学习任务暂未开放。</p></section>;
  if (error && !data) return <div className="learning-page" role="alert"><p>{error}</p><button className="dl-secondary" onClick={()=>setReload(value=>value+1)}>重新读取学习任务</button></div>;
  if (!data || !gateway) return entry ? null : <p className="learning-page" role="status">正在读取学习任务…</p>;
  if (entry) return <LearningEntry actor={data.actor} courses={data.courses} gateway={gateway}/>;
  const arrange=async(event:React.FormEvent)=>{
    event.preventDefault();
    if(saving.current)return;
    const course=data.assignableCourses.find(c=>JSON.stringify([c.id,c.version])===courseKey);
    if(!course||!learner)return;
    const payload=JSON.stringify({staff_id:Number(learner),course_id:course.id,course_version:course.version});
    if(pending.current?.payload!==payload)pending.current={payload,key:crypto.randomUUID()};
    saving.current=true;setBusy(true);setError('');setAssigned(false);
    try {
      assertIdentity(data.actor);
      const response=await client.post<Snapshot>('/staff-learning/assignments',{...JSON.parse(payload),request_id:pending.current.key});
      const snapshot=checkedSnapshot(response.data,data.actor);
      if(alive.current){setData(snapshot);setAssigned(true);pending.current=undefined;}
    }catch(failure){if(alive.current)setError(requestErrorMessage(failure));}
    finally{saving.current=false;if(alive.current)setBusy(false);}
  };
  const arrangeForm=data.actor.role==='manager' && <section className="dl-arrange">
      <button className="dl-secondary" aria-expanded={assigning} onClick={()=>setAssigning(value=>!value)}>安排学习</button>
      {assigning&&<form onSubmit={arrange}>
        <label htmlFor="learning-person">技师</label><select id="learning-person" value={learner} disabled={busy} onChange={e=>{setLearner(e.target.value);pending.current=undefined;setAssigned(false);}} required><option value="">选择本店技师</option>{data.roster.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select>
        <label htmlFor="learning-course">课程</label><select id="learning-course" value={courseKey} disabled={busy} onChange={e=>{setCourseKey(e.target.value);pending.current=undefined;setAssigned(false);}} required><option value="">选择课程</option>{data.assignableCourses.map(c=><option key={JSON.stringify([c.id,c.version])} value={JSON.stringify([c.id,c.version])}>{data.courses.find(v=>v.id===c.id&&v.version===c.version)?.title}</option>)}</select>
        <button className="dl-primary" disabled={busy||!learner||!courseKey}>{busy?'正在安排…':'确认安排'}</button>
        {assigned&&<p role="status">已安排，技师进入本次学习即可查看；相同课程版本不会重复分配。</p>}
        {error&&<p role="alert">{error}</p>}
      </form>}
    </section>;
  return <DailyLearningPage key={identityKey+':'+data.assignments.map(a=>a.id).join(':')} actor={data.actor} courses={data.courses} gateway={gateway} arrange={arrangeForm} storeName={getStaff()?.store_name}/>;
}
