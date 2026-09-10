import {useEffect, useState} from 'react';
import {Alert, Button, Drawer, Empty, Spin, Typography} from 'antd';
import {getOwnRecordVersions} from '../api';

export default function ProjectRecordHistory({recordId,onClose,onEdit}:{recordId:number|null;onClose:()=>void;onEdit:(task:any)=>void}) {
  const [data,setData]=useState<any>();
  const [page,setPage]=useState(1);
  const [failed,setFailed]=useState(false);
  const [reload,setReload]=useState(0);
  useEffect(()=>setPage(1),[recordId]);
  useEffect(()=>{
    if(!recordId)return;
    let active=true;setData(undefined);setFailed(false);
    getOwnRecordVersions(recordId,page).then(result=>{if(active)setData(result.data);}).catch(()=>{if(active)setFailed(true);});
    return ()=>{active=false;};
  },[recordId,page,reload]);
  return <Drawer title="本次服务记录" open={recordId!==null} onClose={onClose} placement="bottom" height="90dvh" className="project-record-sheet">
    <div className="project-record-content">
      <p>仅本人可见。更正会新增版本，原记录保留。</p>
      {failed?<Alert type="error" message="历史记录加载失败" action={<Button onClick={()=>setReload(value=>value+1)}>重试</Button>} />:!data?<Spin />:!data.items.length?<Empty description="暂无记录" />:data.items.map((item:any,index:number)=><section key={item.id}>
        <h2>{page===1 && index===0?'最近保存':'此前版本'}</h2>
        <p>{new Date(item.created_at).toLocaleString('zh-CN')} · {item.customer_confirmed?'顾客已确认':'尚未向顾客确认'}</p>
        {(item.service_lines || []).map((line:string,i:number)=><p key={i}>{line}</p>)}
        {item.profile?.recording_outcome==='no_additional_notes' && <p>本次没有新情况</p>}
        {item.profile?.heat_note && <Typography.Paragraph style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>热敷补充：{item.profile.heat_note}</Typography.Paragraph>}
        {item.profile?.service_note && <Typography.Paragraph style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>补充：{item.profile.service_note}</Typography.Paragraph>}
        {page===1 && index===0 && <Button onClick={()=>onEdit({...data.task,record:item})}>更正本次记录</Button>}
      </section>)}
      <div className="project-record-actions">{page>1 && <Button onClick={()=>setPage(value=>value-1)}>较新记录</Button>}{data?.has_more && <Button onClick={()=>setPage(value=>value+1)}>更早记录</Button>}</div>
    </div>
  </Drawer>;
}
