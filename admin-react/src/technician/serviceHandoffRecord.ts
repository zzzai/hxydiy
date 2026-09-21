export type Communication = 'quiet' | 'chat';
export type BodyRegion = 'neck_shoulder' | 'waist_back' | 'leg' | 'knee' | 'foot';
export type NextAction = 'focus' | 'lighter' | 'avoid' | 'confirm';
export type SessionChange = 'pressure_lighter' | 'pressure_stronger' | 'temperature_lower' | 'temperature_higher' | 'pace_slower' | 'ended_early';
export type AgeBand = 'age_25_29' | 'age_30_34' | 'age_35_39' | 'age_40_44' | 'age_45_49' | 'age_50_59' | 'age_60_plus';
export type Gender = 'male' | 'female';

export type ServiceHandoff = {
  schema_version: 7;
  taxonomy_version: 'service_handoff_v1';
  communication?: Communication;
  body_focus: Array<{ region: BodyRegion; next_action?: NextAction }>;
  session_changes: SessionChange[];
  basic_info?: { age_band?: AgeBand; gender?: Gender };
  private_note: string;
  recording_outcome?: 'no_additional_notes';
};

export const makeHandoff = (): ServiceHandoff => ({
  schema_version: 7,
  taxonomy_version: 'service_handoff_v1',
  body_focus: [],
  session_changes: [],
  private_note: '',
});

export function hasHandoffContent(record: ServiceHandoff): boolean {
  return Boolean(
    record.communication
    || record.body_focus.length
    || record.session_changes.length
    || record.basic_info?.age_band
    || record.basic_info?.gender
    || record.private_note.trim(),
  );
}

export function buildHandoffPayload(userId: number, selectionSessionId: string, record: ServiceHandoff, confirmed: boolean, correctionOfId?: number) {
  if (record.body_focus.length > 3) throw new Error('重点部位最多记录三处');
  if (new Set(record.body_focus.map((item) => item.region)).size !== record.body_focus.length) throw new Error('同一部位只记录一次');
  if (record.body_focus.some((item) => !item.next_action)) throw new Error('请为每个重点部位选择下次处理方式');
  if (record.recording_outcome && hasHandoffContent(record)) throw new Error('本次没有新情况不能与其他内容同时保存');
  if (!record.recording_outcome && !hasHandoffContent(record)) throw new Error('请至少记录一项，或选择本次没有新情况');
  return {
    user_id: userId,
    selection_session_id: selectionSessionId,
    schema_version: 7 as const,
    taxonomy_version: 'service_handoff_v1' as const,
    customer_confirmed: confirmed,
    profile: {
      ...record,
      private_note: record.private_note.trim(),
      body_focus: record.body_focus.map((item) => ({ region: item.region, next_action: item.next_action! })),
    },
    signals: [],
    note: '',
    ...(correctionOfId ? { correction_of_id: correctionOfId, correction_reason: '更正本人本次服务记录' } : {}),
  };
}

const regionLabels: Record<BodyRegion, string> = { neck_shoulder: '肩颈', waist_back: '腰背', leg: '腿部', knee: '膝盖', foot: '足部' };
const actionLabels: Record<NextAction, string> = { focus: '下次重点加强', lighter: '下次轻一些', avoid: '下次避开', confirm: '下次先确认' };
const changeLabels: Record<SessionChange, string> = { pressure_lighter: '本次力度调轻', pressure_stronger: '本次力度调重', temperature_lower: '本次温度调低', temperature_higher: '本次温度调高', pace_slower: '本次节奏放慢', ended_early: '本次提前结束' };

export function handoffPreview(record: ServiceHandoff): string[] {
  const lines: string[] = [];
  if (record.communication) lines.push(record.communication === 'quiet' ? '顾客想安静休息' : '顾客愿意聊天');
  lines.push(...record.body_focus.filter((item) => item.next_action).map((item) => `${regionLabels[item.region]}${actionLabels[item.next_action!]}`));
  lines.push(...record.session_changes.map((item) => changeLabels[item]));
  return lines;
}
