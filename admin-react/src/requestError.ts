type RequestError = { code?: string; status?: number; response?: { status?: number; data?: { detail?: unknown } }; detail?: unknown };

const codeMessages: Record<string, string> = {
  HEADQUARTERS_ADMIN_REQUIRED: '仅总部管理员可以修改此内容，请切换有权限的账号。',
  STORE_SCOPE_DENIED: '当前账号不能操作这个门店，请切换回所属门店。',
  STORE_SCOPE_REQUIRED: '当前账号尚未绑定门店，请联系管理员处理。',
  STORE_REQUIRED: '请先选择已建立的门店。',
  MANAGER_REQUIRED: '当前操作需要门店管理权限。',
};

export function requestErrorMessage(error: unknown): string {
  const value = error as RequestError | null;
  const status = Number(value?.response?.status ?? value?.status ?? 0);
  const detail = value?.response?.data?.detail ?? value?.detail;
  if (status === 401) return '登录已失效，请重新登录后继续。';
  if (status >= 500) return '服务暂时不可用，请稍后重试；填写内容请先保留。';
  if (value?.code === 'ECONNABORTED' || value?.code === 'ETIMEDOUT') return '请求超时，暂未确认操作结果。请保留填写内容，稍后重试。';
  if (!status) return '暂时无法连接服务器，请检查网络后重试。';
  const code = typeof detail === 'object' && detail !== null && !Array.isArray(detail) ? (detail as { code?: string }).code : undefined;
  if (code && codeMessages[code]) return codeMessages[code];
  if (status === 400 && detail === '总部上传必须指定门店') return '请先选择项目所属门店，再上传图片。';
  if (status === 422 && Array.isArray(detail)) {
    const fields: Record<string, string> = { name: '名称', code: '编码', summary: '简介', description: '说明', prices: '价格', image_url: '图片地址', duration_min: '服务时长', store_id: '目标门店', max_select: '最多选择数量', min_select: '最少选择数量' };
    const known = detail.filter(item => item && Array.isArray(item.loc)).map(item => fields[String(item.loc[1])]).filter(Boolean);
    if (known.length) return `${[...new Set(known)].join('、')}未通过校验，请检查长度、必填项和数字范围。`;
  }
  if (status === 403) return '当前账号没有此操作权限，请联系管理员。';
  if (status === 404) return '这条内容已不存在或不在当前门店，请刷新列表。';
  if (status === 409) return '内容状态已发生变化，请保留修改并刷新后核对。';
  if (status === 422) return '填写内容未通过校验，请检查必填项、数字范围和选项配置。';
  if (status === 429) return '操作过于频繁，请稍后再试。';
  // Never surface raw response bodies, validation inputs, SQL, or internal field names.
  return '本次操作未完成，请保留填写内容后重试。';
}
