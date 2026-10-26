export const AUDIT_ACTIONS: Record<string, string> = {
  create_project: '新建服务项目', update_project: '修改服务项目', duplicate_project: '复制服务项目',
  create_option_group: '新增可选内容分组', update_option_group: '修改可选内容分组', delete_option_group: '删除可选内容分组',
  create_option_choice: '新增顾客选项', update_option_choice: '修改顾客选项', delete_option_choice: '删除顾客选项',
  create_catalog_draft: '创建项目编辑草稿', copy_project_option_groups: '复制项目可选内容',
  publish_catalog_version: '发布项目可选内容', media_upload: '上传图片', media_delete: '删除图片',
  create_segment: '建立顾客分群', create_automation: '保存自动化规则', update_page_content: '修改顾客页面内容',
  wecom_feedback_notify: '企微评价通知',
  publish_page_content: '发布顾客页面内容', rollback_page_content: '恢复页面内容',
};
export const ENTITY_LABELS: Record<string, string> = { service_feedback: '服务评价', visit_feedback: '到店扫码评价', project_catalog_version: '项目目录版本', project: '服务项目', project_option_group: '可选内容分组', project_option_choice: '顾客选项', media: '图片', page_content: '页面内容', segment: '顾客分群', automation: '自动化规则', staff: '员工账号', order: '服务订单', selection: '顾客选单', store: '门店' };
export const TRIGGER_LABELS: Record<string, string> = { new_user: '新用户注册', first_order: '首次服务完成', order_completed: '服务完成', no_visit_30d: '30 天未访问', member_expiring: '会员即将到期', high_spender: '高客单价' };
export const ACTION_LABELS: Record<string, string> = { grant_coupon: '赠送优惠券', add_tag: '添加顾客标签', remove_tag: '移除顾客标签', send_notification: '发送通知' };
const DETAIL_FIELDS: Record<string, string> = { store_id: '门店编号', project_id: '项目编号', catalog_version_id: '目录版本编号', version: '版本', group_id: '分组编号', duplicate_project_id: '新项目编号', size_bytes: '文件大小（字节）', count: '数量', affected_count: '影响数量', assignment_id: '工作区编号' };
export function auditDetailRows(detail: unknown, action?: string): Array<{ label: string; value: string }> {
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return [];
  if (action === 'wecom_feedback_notify') {
    const value = detail as Record<string, unknown>;
    const statuses: Record<string, string> = { started: '已发起，待确认结果', accepted: '企微已受理（不代表已读）', partial: '部分接收人已受理', rejected: '企微未接收', unknown: '发送结果未确认，勿盲目重发', no_recipient: '无可通知的本店店长' };
    const rows = [{ label: '通知结果', value: statuses[String(value.status)] || '结果待核验' }];
    const counts: Record<string, string> = { recipient_count: '目标人数', accepted_count: '企微受理人数', invalid_count: '未受理人数' };
    for (const [key, label] of Object.entries(counts)) {
      if (typeof value[key] === 'number' && Number.isSafeInteger(value[key]) && value[key] >= 0) rows.push({ label, value: String(value[key]) });
    }
    return rows;
  }
  return Object.entries(detail).flatMap(([key, value]) => DETAIL_FIELDS[key] && typeof value === 'number' && Number.isFinite(value) ? [{ label: DETAIL_FIELDS[key], value: String(value) }] : []);
}
export function segmentConditions(values: { tags?: string[]; memberOnly?: boolean }): { tags?: string[]; is_member?: true } {
  return { ...(values.tags?.length ? { tags: [...new Set(values.tags)] } : {}), ...(values.memberOnly ? { is_member: true as const } : {}) };
}
export function segmentSummary(conditions: unknown): string[] {
  if (!conditions || typeof conditions !== 'object' || Array.isArray(conditions)) return ['旧版条件待核验，原配置保留'];
  const value = conditions as Record<string, unknown>;
  const result: string[] = [];
  if (Array.isArray(value.tags) && value.tags.every(tag => typeof tag === 'string')) {
    if (value.tags.length) result.push(`具有任一标签：${value.tags.join('、')}`);
  } else if (value.tags) result.push('旧版标签条件待核验');
  if (value.is_member === true) result.push('具有会员标记');
  if (Object.keys(value).some(key => !['tags', 'is_member'].includes(key))) result.push('含旧版附加条件，统计结果需核验');
  return result.length ? result : ['本店关联顾客，不限标签与会员标记'];
}
export function automationActionText(action: unknown): string {
  if (!action || typeof action !== 'object') return '旧版动作待核验';
  const value = action as { type?: string; tag_id?: number };
  const label = ACTION_LABELS[value.type || ''];
  if (!label) return '旧版动作待核验';
  return ['add_tag', 'remove_tag'].includes(value.type || '') && Number.isInteger(value.tag_id) ? `${label} · 标签编号 ${value.tag_id}` : label;
}
export function disabledTagRule(values: { name: string; description?: string; trigger_event: string; action: 'add_tag' | 'remove_tag'; tag_id: number; cooldown_days?: number }) {
  return { name: values.name.trim(), description: values.description || '', trigger_event: values.trigger_event, actions: [{ type: values.action, tag_id: values.tag_id }], cooldown_days: values.cooldown_days || 0, is_enabled: false };
}
