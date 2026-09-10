export type ProjectRecord = {
  schema_version: 6; taxonomy_version: 'service_record_v1';
  template: 'herbal_signature_v1' | 'general_v1';
  water?: {request?: string; action?: string; feedback?: string};
  massage?: {region: string; side: string; request?: string; action?: string; feedback?: string}[];
  heat?: string; heat_note?: string; communication?: string; service_note?: string;
  recording_outcome?: 'no_additional_notes';
};
export function makeRecord(items: {name?: string;code?:string}[]): ProjectRecord {
  return {schema_version:6, taxonomy_version:'service_record_v1', template:items.some(item=>item.code==='hxy-xiaoqi-90' || !item.code && item.name==='招牌草本泡')?'herbal_signature_v1':'general_v1'};
}
export function hasRecordContent(value: ProjectRecord): boolean {
  return Boolean(value.water && Object.values(value.water).some(Boolean) || value.massage?.length || value.heat || value.heat_note?.trim() || value.communication || value.service_note?.trim());
}
export function buildRecordPayload(userId: number, sessionId: string, value: ProjectRecord, confirmed: boolean, correctionId?: number) {
  if (value.recording_outcome && (hasRecordContent(value) || confirmed)) throw new Error('本次没有新情况不能与内容或顾客确认一起保存');
  if (!value.recording_outcome && !hasRecordContent(value)) throw new Error('请记录一项内容');
  const massage = value.massage || [];
  if (massage.some(item=>!item.region || ![item.request,item.action,item.feedback].some(Boolean))) throw new Error('请填写所选部位的要求、处理或反馈，或删除空条目');
  if (new Set(massage.map(item=>item.region+':'+item.side)).size !== massage.length) throw new Error('同一部位和侧别只记录一次');
  return {user_id:userId, selection_session_id:sessionId, schema_version:6 as const, taxonomy_version:'service_record_v1' as const,
    customer_confirmed:confirmed, profile:value, signals:[], note:'',
    ...(correctionId ? {correction_of_id:correctionId, correction_reason:'技师更正本次服务记录'} : {})};
}
