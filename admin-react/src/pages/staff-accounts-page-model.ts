export type StaffAccountRole = 'manager' | 'staff';
export type StaffAccountStatus = 'active' | 'disabled';

export type StaffAccount = {
  id: number;
  username: string;
  name: string;
  role: StaffAccountRole;
  store_id: number;
  status: StaffAccountStatus;
  created_at: string | null;
};

export type StaffAccountForm = {
  username?: string;
  password?: string;
  name: string;
  role: StaffAccountRole;
  store_id: number;
  status: StaffAccountStatus;
};

const roleMeta: Record<StaffAccountRole, { label: string; color: string }> = {
  manager: { label: '店长', color: 'blue' },
  staff: { label: '门店员工', color: 'default' },
};

const statusMeta: Record<StaffAccountStatus, { label: string; color: string }> = {
  active: { label: '在职可登录', color: 'green' },
  disabled: { label: '已停用', color: 'default' },
};

export function getStaffAccountRoleMeta(role: StaffAccountRole) {
  return roleMeta[role];
}

export function getStaffAccountStatusMeta(status: StaffAccountStatus) {
  return statusMeta[status];
}

export function staffAccountPayload(values: StaffAccountForm, editing: boolean) {
  const password = values.password?.trim();
  const payload = {
    name: values.name.trim(),
    role: values.role,
    store_id: Number(values.store_id),
    status: values.status,
    ...(password ? { password } : {}),
  };
  return editing ? payload : { ...payload, username: values.username?.trim() || '' };
}
