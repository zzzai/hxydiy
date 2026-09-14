export interface ServiceReferenceDisplay {
  version: string;
  groups: Array<{ title: string; items: Array<{ label: string; value: string }> }>;
  collapsedQuote: string;
}

const LABELS: Record<string, string> = {
  neck_shoulder: '肩颈', waist_hip: '腰臀', legs: '腿部', abdomen: '腹部', feet: '足部', full_relaxation: '整体放松', gentle: '轻柔', medium: '适中', strong: '偏强', lower: '偏低', higher: '偏高',
  suitable: '本次合适', better_after_adjustment: '调整后更合适', adjust_next_time: '下次需调整', repeat_current: '延续本次', confirm_on_arrival: '到店再确认',
  quiet: '希望安静', chat: '愿意聊天', explain_before_action: '希望先沟通',
  pressure_lighter: '减轻力度', pressure_stronger: '加强力度', pace_slower: '放慢节奏', temperature_lower: '调低温度', temperature_higher: '调高温度', focus_area: '重点照顾', avoid_area: '避开该处', end_early: '提前结束',
  body_reconfirm: '服务前再确认',
  no_additional_notes: '本次无补充（已完成记录）',
};

const labelValue = (field: string, value: unknown) => {
  const knownLabel = (code: unknown) => typeof code === 'string' && Object.prototype.hasOwnProperty.call(LABELS, code) ? LABELS[code] : '';
  if (Array.isArray(value)) return value.map(knownLabel).filter(Boolean).join('、');
  return knownLabel(value);
};

export function buildServiceReferenceDisplay(record: any): ServiceReferenceDisplay {
  const profile = record?.profile || {};
  const reported = profile.customer_reported || {};
  const observed = profile.technician_observed || {};
  const rows: Array<[string, Array<[string, unknown]>]> = [
    ['服务偏好', [['沟通方式', reported.communication_preference], ['本次重点', reported.focus_areas], ['避开或谨慎', reported.avoid_areas], ['力度', reported.force_preference], ['温度', reported.temperature_preference]]],
    ['本次反馈与下次', [['本次调整', observed.service_adjustments], ['服务反馈', observed.service_feedback], ['下次安排', profile.next_visit?.plan]]],
    ['记录完成情况', [['完成情况', observed.recording_outcome]]],
    ...(((record?.schema_version === 4 && record?.taxonomy_version === 'service_reference_v3') || (record?.schema_version === 5 && record?.taxonomy_version === 'service_reference_v4')) && (record?.body_reconfirm_required === true || (Array.isArray(reported.body_service_notes) && reported.body_service_notes.length)) ? [['身体服务提醒', [['下次服务', 'body_reconfirm']]]] as Array<[string, Array<[string, unknown]>]> : []),
  ];
  const groups = rows.map(([title, values]) => ({
    title,
    items: values.map(([label, value]) => ({ label, value: labelValue(label, value) })).filter(item => Boolean(item.value)),
  })).filter(group => group.items.length > 0);
  const knownVersion = (record?.schema_version === 3 && record?.taxonomy_version === 'service_reference_v2')
    || (record?.schema_version === 2 && record?.taxonomy_version === 'service_reference_v1')
    || (record?.schema_version === 4 && record?.taxonomy_version === 'service_reference_v3')
    || (record?.schema_version === 5 && record?.taxonomy_version === 'service_reference_v4');
  return {
    version: knownVersion ? `v${record.schema_version} · ${record.taxonomy_version}` : '',
    groups,
    collapsedQuote: '',
  };
}
