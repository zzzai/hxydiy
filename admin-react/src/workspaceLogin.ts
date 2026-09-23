export type StaffSummary = {
  id: number;
  name: string;
  role: string;
  store_id: number | null;
  technician_id: number | null;
  store_name: string;
};

export type WorkspaceGrant = {
  assignment_id: number;
  role: 'brand_admin' | 'hq_operator' | 'store_manager' | 'store_staff';
  scope_type: 'brand' | 'store';
  scope_id: number | null;
  scope_name: string;
};

export type StaffLoginResponse = {
  token: string;
  selector_token: string | null;
  workspaces: WorkspaceGrant[];
  staff: StaffSummary;
};

export type WorkspaceSelectResponse = {
  token: string;
  workspace: WorkspaceGrant;
  staff: StaffSummary;
};

export type ReadyStaffSession = { kind: 'ready'; token: string; staff: StaffSummary };
export type WorkspaceSelection = { kind: 'select'; selectorToken: string; workspaces: WorkspaceGrant[] };

const sessionRoleByWorkspace = {
  brand_admin: 'admin',
  hq_operator: 'staff',
  store_manager: 'manager',
  store_staff: 'staff',
} as const;

function sessionStaff(staff: StaffSummary): StaffSummary {
  const role = staff.role as WorkspaceGrant['role'];
  return { ...staff, role: sessionRoleByWorkspace[role] ?? staff.role };
}

export function interpretStaffLogin(response: StaffLoginResponse): ReadyStaffSession | WorkspaceSelection {
  if (response.workspaces.length > 1) {
    if (!response.selector_token) throw new Error('工作区选择凭证无效，请重新登录');
    return { kind: 'select', selectorToken: response.selector_token, workspaces: response.workspaces };
  }
  if (!response.token || !response.staff?.role) throw new Error('登录响应无效，请重新登录');
  return { kind: 'ready', token: response.token, staff: sessionStaff(response.staff) };
}

export function finishWorkspaceSelection(response: WorkspaceSelectResponse, assignmentId: number): ReadyStaffSession {
  if (
    response.workspace.assignment_id !== assignmentId || !response.token || !response.staff?.role ||
    response.staff.role !== response.workspace.role ||
    response.staff.store_id !== response.workspace.scope_id
  ) {
    throw new Error('工作区选择结果不匹配，请重新登录');
  }
  return { kind: 'ready', token: response.token, staff: sessionStaff(response.staff) };
}

export function storeStaffSession(storage: Pick<Storage, 'setItem'>, session: ReadyStaffSession): void {
  storage.setItem('hxy_admin_token', session.token);
  storage.setItem('hxy_admin_staff', JSON.stringify(session.staff));
}
