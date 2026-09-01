import { useState } from 'react';
import { App, Button, Dropdown, Modal, Space, Tag, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { CheckCircleOutlined, KeyOutlined, MoreOutlined, PlusOutlined, ReloadOutlined, StopOutlined, UserSwitchOutlined } from '@ant-design/icons';
import { ModalForm, PageContainer, ProFormDigit, ProFormSelect, ProFormText, ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { createTechnician, disableTechnicianLogin, getStaff, inviteTechnician, rehireTechnician, resetTechnicianLogin, resignTechnician, restoreTechnicianLogin } from '../api';
import { canManageConfiguration, getStoreId } from '../auth';
import { refineDataProvider } from '../core/dataProvider/refine';
import { resources } from '../core/resources';

const businessStatus: Record<string, string> = { available: '在岗', busy: '服务中', off: '休息', resigned: '离职' };
const loginStatus: Record<string, { label: string; color: string }> = {
  not_opened: { label: '未开通', color: 'default' }, invited: { label: '待激活', color: 'gold' }, active: { label: '正常', color: 'green' }, disabled: { label: '停用', color: 'red' }, resigned: { label: '离职', color: 'default' },
};
const levelOptions = ['初级', '中级', '高级', '督导'].map((value) => ({ value, label: value }));
type CredentialResult = { username?: string; token?: string; expires_at?: string };

export default function TechsPage() {
  const { message } = App.useApp();
  const staff = getStaff();
  const canManage = canManageConfiguration(staff?.role);
  const [actionRef] = useState<React.MutableRefObject<ActionType | undefined>>({ current: undefined });
  const [open, setOpen] = useState(false);

  const showCredential = (result: CredentialResult) => Modal.info({
    title: '登录凭证已生成',
    content: <Space direction="vertical" size={4} style={{ width: '100%' }}><div><strong>账号：</strong>{result.username || '—'}</div><div style={{ wordBreak: 'break-all' }}><strong>激活凭证：</strong>{result.token || '—'}</div><div><strong>失效时间：</strong>{result.expires_at ? new Date(result.expires_at).toLocaleString('zh-CN') : '—'}</div><div style={{ color: '#a15c00' }}>仅显示一次，请交给技师在手机端完成首次激活或重置密码。</div><Button icon={<KeyOutlined />} onClick={async () => { if (result.token) await navigator.clipboard?.writeText(result.token); message.success('激活凭证已复制'); }}>复制激活凭证</Button></Space>,
    okText: '知道了',
  });

  const runAction = async (record: any, action: string) => {
    try {
      if (action === 'invite') showCredential((await inviteTechnician(record.id)).data);
      if (action === 'reset') showCredential((await resetTechnicianLogin(record.id)).data);
      if (action === 'rehire') showCredential((await rehireTechnician(record.id)).data);
      if (action === 'disable') await disableTechnicianLogin(record.id);
      if (action === 'restore') await restoreTechnicianLogin(record.id);
      if (action === 'resign') await resignTechnician(record.id, '店长办理离职');
      message.success('账号状态已更新');
      actionRef.current?.reload();
    } catch { /* API interceptor already presents the server error. */ }
  };
  const confirmAction = (record: any, action: string, title: string, content: string) => Modal.confirm({ title, content, okText: '确认', cancelText: '取消', onOk: () => runAction(record, action) });
  const actionMenu = (record: any): MenuProps['items'] => {
    const status = record.login_status;
    if (record.status === 'resigned') return [{ key: 'rehire', icon: <UserSwitchOutlined />, label: '返聘并重新开通', onClick: () => confirmAction(record, 'rehire', '确认返聘？', '将恢复技师档案并生成新的首次激活凭证，旧密码和旧会话不会复用。') }];
    const items: MenuProps['items'] = [];
    if (status === 'not_opened' || status === 'invited') items.push({ key: 'invite', icon: <KeyOutlined />, label: status === 'invited' ? '重新开通并生成凭证' : '开通登录', onClick: () => confirmAction(record, 'invite', '确认开通登录？', '系统将生成一次性激活凭证，技师需在手机端设置密码。') });
    if (status === 'active' || status === 'disabled') items.push({ key: 'reset', icon: <KeyOutlined />, label: '重置登录', onClick: () => confirmAction(record, 'reset', '确认重置登录？', '旧密码和旧登录会话将立即失效，技师需使用新凭证设置密码。') });
    if (status === 'disabled') items.push({ key: 'restore', icon: <CheckCircleOutlined />, label: '恢复账号', onClick: () => confirmAction(record, 'restore', '确认恢复账号？', '恢复后原密码仍可用于日常登录。') });
    else if (status === 'active' || status === 'invited') items.push({ key: 'disable', icon: <StopOutlined />, label: '停用账号', danger: true, onClick: () => confirmAction(record, 'disable', '确认停用账号？', '停用会立即撤销登录能力，但保留技师档案、历史服务和审计。') });
    items.push({ key: 'resign', icon: <StopOutlined />, label: '办理离职', danger: true, onClick: () => confirmAction(record, 'resign', '确认办理离职？', '存在进行中服务时操作会被拒绝；离职后账号停用且历史数据保留。') });
    return items;
  };

  const columns: ProColumns<any>[] = [
    { title: '姓名', dataIndex: 'name', fixed: 'left', width: 120 },
    { title: '编码', dataIndex: 'code', width: 110, copyable: true },
    { title: '账号', dataIndex: 'username', width: 130, render: (_, record) => record.username || '—' },
    { title: '业务状态', dataIndex: 'status', width: 100, valueType: 'select', valueEnum: Object.fromEntries(Object.entries(businessStatus).map(([value, text]) => [value, { text }])), render: (_, record) => <Tag color={record.status === 'available' ? 'green' : record.status === 'resigned' ? 'default' : 'gold'}>{businessStatus[record.status] || record.status}</Tag> },
    { title: '登录状态', dataIndex: 'login_status', width: 100, valueType: 'select', valueEnum: Object.fromEntries(Object.entries(loginStatus).map(([value, item]) => [value, { text: item.label }])), render: (_, record) => { const item = loginStatus[record.login_status] || loginStatus.not_opened; return <Tag color={item.color}>{item.label}</Tag>; } },
    { title: '等级', dataIndex: 'level', width: 80, render: (_, record) => <Tag>{record.level}</Tag> },
    ...(canManage ? [{ title: '操作', key: 'actions', width: 72, fixed: 'right' as const, render: (_: unknown, record: any) => <Tooltip title="账号操作"><Dropdown trigger={['click']} menu={{ items: actionMenu(record) }}><Button type="text" aria-label={`操作${record.name}`} icon={<MoreOutlined />} /></Dropdown></Tooltip> }] : []),
  ];

  return <PageContainer title="技师管理" content="维护技师档案和登录账号生命周期。" extra={[<Button key="refresh" icon={<ReloadOutlined />} onClick={() => actionRef.current?.reload()}>刷新</Button>, ...(canManage ? [<Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建技师</Button>] : [])]}>
    <ProTable<any> actionRef={actionRef} rowKey="id" columns={columns} search={{ labelWidth: 'auto', defaultCollapsed: true }} pagination={{ defaultPageSize: 20, showSizeChanger: true }} request={async (params) => {
      const result = await refineDataProvider.getList({ resource: resources.technicians, pagination: { currentPage: params.current, pageSize: params.pageSize, mode: 'server' }, filters: [{ field: 'status', operator: 'eq' as const, value: params.status }, { field: 'level', operator: 'eq' as const, value: params.level }], sorters: [] });
      return { success: true, data: result.data, total: result.total };
    }} options={{ density: true, fullScreen: true, reload: true, setting: true }} scroll={{ x: 780 }} />
    <ModalForm title="新建技师档案" open={open} width={560} modalProps={{ destroyOnClose: true }} onOpenChange={setOpen} onFinish={async (values) => { await createTechnician({ ...values, store_id: getStoreId(staff) }); message.success('已创建技师档案'); actionRef.current?.reload(); return true; }}>
      <ProFormText name="code" label="编码" rules={[{ required: true, message: '请输入编码' }]} />
      <ProFormText name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]} />
      <ProFormText name="phone" label="手机号" />
      <ProFormSelect name="gender" label="性别" options={[{ value: '男', label: '男' }, { value: '女', label: '女' }]} />
      <ProFormSelect name="level" label="等级" initialValue="初级" options={levelOptions} />
      <ProFormDigit name="default_commission_rate" label="提成比例" initialValue={0.3} min={0} max={1} fieldProps={{ step: 0.05 }} />
    </ModalForm>
  </PageContainer>;
}
