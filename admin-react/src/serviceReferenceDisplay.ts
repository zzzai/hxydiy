export interface ServiceReferenceDisplay {
  version: string;
  groups: Array<{ title: string; items: Array<{ label: string; value: string }> }>;
  collapsedQuote: string;
}

const LABELS: Record<string, string> = {
  '18_24': '18-24岁', '25_34': '25-34岁', '35_44': '35-44岁', '45_54': '45-54岁', '55_64': '55-64岁', '65_plus': '65岁以上',
  slim: '偏瘦', sturdy: '偏壮', shorter: '偏矮', taller: '偏高', desk_work: '久坐办公', standing_work: '久站服务', frequent_driving: '经常驾驶', physical_labor: '体力劳动', family_care: '照护家庭', freelance: '自由职业', retired: '退休', other: '其他',
  good: '良好', poor: '较差', long_term_condition: '顾客提及长期身体情况', recent_discomfort_recovery: '顾客提及近期不适或恢复情况', skin_sensitivity: '顾客提及皮肤敏感或接触偏好', medication_mentioned: '顾客提及正在用药', pregnancy_postpartum: '顾客提及孕期或产后阶段', other_reconfirm: '其他需再次确认的情况',
  neck_shoulder: '肩颈', waist_hip: '腰臀', legs: '腿部', abdomen: '腹部', feet: '足部', full_relaxation: '整体放松', gentle: '轻柔', medium: '适中', strong: '偏强', lower: '偏低', higher: '偏高',
  quick: '较快', gradual: '逐渐', tense: '始终较紧张', suitable: '本次合适', better_after_adjustment: '调整后更合适', adjust_next_time: '下次需调整', repeat_current: '延续本次', confirm_on_arrival: '到店再确认',
  price: '价格', quality: '品质', environment: '环境', efficiency: '效率', fixed_technician: '固定技师', fixed_time: '固定时段', value: '实惠优先', experience: '体验优先', unexpressed: '未表达',
};

const labelValue = (field: string, value: unknown) => {
  if (field === '身高区间' && value === 'average') return '适中';
  if (field === '体型' && value === 'balanced') return '匀称';
  if (field === '预算倾向' && value === 'balanced') return '平衡';
  if (field === '睡眠自述' && value === 'average') return '一般';
  const knownLabel = (code: unknown) => typeof code === 'string' && Object.prototype.hasOwnProperty.call(LABELS, code) ? LABELS[code] : '';
  if (Array.isArray(value)) return value.map(knownLabel).filter(Boolean).join('、');
  return knownLabel(value);
};

export function buildServiceReferenceDisplay(record: any): ServiceReferenceDisplay {
  const profile = record?.profile || {};
  const reported = profile.customer_reported || {};
  const personal = reported.personal_context || {};
  const work = reported.work_lifestyle || {};
  const related = reported.service_related_context || {};
  const consumption = reported.communication_consumption || {};
  const observed = profile.technician_observed || {};
  const rows: Array<[string, Array<[string, unknown]>]> = [
    ['个人概况', [['年龄段', personal.age_band], ['体型', personal.build], ['身高区间', personal.height_band]]],
    ['工作与生活', [['职业场景', work.occupation_contexts], ['睡眠自述', work.sleep_quality]]],
    ['服务相关情况', [['需再次确认', related.contexts]]],
    ['服务偏好', [['本次重点', reported.focus_areas], ['避开或谨慎', reported.avoid_areas], ['力度', reported.force_preference], ['温度', reported.temperature_preference]]],
    ['本次反应', [['放松过程', observed.session_response?.relaxation], ['服务反馈', observed.service_feedback]]],
    ['下次与沟通', [['下次建议', profile.next_visit?.plan], ['决策关注', consumption.decision_priorities], ['预算倾向', consumption.budget_preference]]],
  ];
  const groups = rows.map(([title, values]) => ({
    title,
    items: values.map(([label, value]) => ({ label, value: labelValue(label, value) })).filter(item => Boolean(item.value)),
  })).filter(group => group.items.length > 0);
  const knownVersion = (record?.schema_version === 3 && record?.taxonomy_version === 'service_reference_v2')
    || (record?.schema_version === 2 && record?.taxonomy_version === 'service_reference_v1');
  return {
    version: knownVersion ? `v${record.schema_version} · ${record.taxonomy_version}` : '',
    groups,
    collapsedQuote: String(related.quote || reported.quote || ''),
  };
}
