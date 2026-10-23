import { useEffect, useState } from 'react';
import { App, Button, Card, DatePicker, Dropdown, Input, Modal, Select, Space, Table, Tag, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { CheckCircleOutlined, KeyOutlined, MoreOutlined, PlusOutlined, ReloadOutlined, StopOutlined, UserSwitchOutlined } from '@ant-design/icons';
import { ModalForm, PageContainer, ProFormDigit, ProFormSelect, ProFormText, ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { approveTechnicianLeave, copyTechnicianShiftWeek, createTechnician, disableTechnicianLogin, getStaff, getTechnicianBoard, getTechnicianHours, getTechnicianLeaveRequests, getTechnicianShifts, inviteTechnician, rehireTechnician, rejectTechnicianLeave, resetTechnicianLogin, resignTechnician, restoreTechnicianLogin, saveTechnicianShift } from '../api';
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
  const [leaveRows, setLeaveRows] = useState<any[]>([]);
  const [leaveLoading, setLeaveLoading] = useState(false);
  const [rejecting, setRejecting] = useState<any>();
  const [rejectNote, setRejectNote] = useState('');
  const [board, setBoard] = useState<any>();
  const [boardLoading, setBoardLoading] = useState(false);
  const [weekStart, setWeekStart] = useState<Dayjs>(dayjs().startOf('week'));
  const [shifts, setShifts] = useState<any[]>([]);
  const [shiftLoading, setShiftLoading] = useState(false);
  const [hoursData, setHoursData] = useState<any>();
  const [hoursLoading, setHoursLoading] = useState(false);

  const loadShifts = async (start = weekStart) => {
    setShiftLoading(true);
    try {
      const response = await getTechnicianShifts(start.format('YYYY-MM-DD'), start.add(6, 'day').format('YYYY-MM-DD'));
      setShifts(response.data?.items || []);
    } catch { /* API interceptor already presents the server error. */ }
    finally { setShiftLoading(false); }
  };

  const loadHours = async (start = weekStart) => {
    setHoursLoading(true);
    try {
      const response = await getTechnicianHours(start.format('YYYY-MM-DD'), start.add(6, 'day').format('YYYY-MM-DD'));
      setHoursData(response.data);
    } catch { /* API interceptor already presents the server error. */ }
    finally { setHoursLoading(false); }
  };

  const changeShift = async (technicianId: number, workDate: string, shiftType: string) => {
    try {
      await saveTechnicianShift({ technician_id: technicianId, work_date: workDate, shift_type: shiftType });
      await loadShifts();
    } catch { /* API interceptor already presents the server error. */ }
  };

  const copyPreviousWeek = () => Modal.confirm({
    title: '复制上一周排班？',
    content: '将上一周的班次复制到本周；已有排班默认跳过，请假和已排服务冲突也会跳过。',
    okText: '确认复制',
    cancelText: '取消',
    onOk: async () => {
      const source = weekStart.subtract(7, 'day');
      const response = await copyTechnicianShiftWeek({ source_start: source.format('YYYY-MM-DD'), target_start: weekStart.format('YYYY-MM-DD') });
      const data = response.data || {};
      message.success(`已复制 ${data.copied || 0} 条；跳过已存在 ${data.skipped_existing || 0}、请假冲突 ${data.skipped_leave || 0}、服务冲突 ${data.skipped_booking || 0}`);
      await loadShifts();
    },
  });

  useEffect(() => { if (canManage) { void loadShifts(); void loadHours(); } }, [canManage, weekStart]);

  const loadBoard = async () => {
    setBoardLoading(true);
    try {
      const response = await getTechnicianBoard();
      setBoard(response.data);
    } catch { /* API interceptor already presents the server error. */ }
    finally { setBoardLoading(false); }
  };

  const loadLeaves = async () => {
    setLeaveLoading(true);
    try {
      const response = await getTechnicianLeaveRequests('submitted');
      setLeaveRows(response.data?.items || []);
    } catch { /* API interceptor already presents the server error. */ }
    finally { setLeaveLoading(false); }
  };

  useEffect(() => { if (canManage) { void loadLeaves(); void loadBoard(); } }, [canManage]);

  const approveLeave = async (row: any) => {
    try {
      await approveTechnicianLeave(row.id);
      message.success('请假申请已批准，技师状态已调整');
      await loadLeaves();
      actionRef.current?.reload();
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      if (detail?.code === 'LEAVE_SCHEDULE_CONFLICT') {
        const orders = (detail.conflicts || []).map((item: any) => `${item.booking_date} ${item.booking_time || ''} ${item.order_no}`).join('、');
        message.error(`${detail.message}${orders ? `：${orders}` : ''}`);
      }
    }
  };

  const rejectLeave = async () => {
    if (!rejecting) return;
    if (rejectNote.trim().length < 2) { message.error('请填写至少 2 个字的驳回原因'); return; }
    try {
      await rejectTechnicianLeave(rejecting.id, rejectNote.trim());
      message.success('请假申请已驳回');
      setRejecting(undefined); setRejectNote('');
      await loadLeaves();
    } catch { /* API interceptor already presents the server error. */ }
  };

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

  const weekDays = Array.from({ length: 7 }, (_, index) => weekStart.add(index, 'day'));
  const shiftsByKey = new Map(shifts.map((shift: any) => [`${shift.technician_id}:${shift.work_date}`, shift]));

  return <PageContainer title="技师管理" content="维护技师档案和登录账号生命周期。" extra={[<Button key="refresh" icon={<ReloadOutlined />} onClick={() => { actionRef.current?.reload(); void loadBoard(); }}>刷新</Button>, ...(canManage ? [<Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建技师</Button>] : [])]}>
    {canManage && <Card title="本周排班" style={{ marginBottom: 16 }} loading={shiftLoading} extra={<Space><DatePicker picker="week" value={weekStart} allowClear={false} onChange={(value) => { if (value) setWeekStart(value.startOf('week')); }} /><Button size="small" onClick={() => copyPreviousWeek()}>复制上一周</Button><Button size="small" onClick={() => void loadShifts()}>刷新排班</Button></Space>}>
      <Table
        rowKey="id"
        size="small"
        pagination={false}
        scroll={{ x: 900 }}
        dataSource={board?.items || []}
        locale={{ emptyText: '当前没有可排班技师' }}
        columns={[
          { title: '技师', dataIndex: 'name', width: 110, fixed: 'left' as const },
          ...weekDays.map((date) => ({
            title: date.format('MM-DD ddd'),
            width: 108,
            render: (_: any, technician: any) => {
              const shift = shiftsByKey.get(`${technician.id}:${date.format('YYYY-MM-DD')}`);
              return <Select
                size="small"
                style={{ width: 96 }}
                placeholder="未排"
                value={shift?.shift_type}
                onChange={(value) => void changeShift(technician.id, date.format('YYYY-MM-DD'), value)}
                options={[
                  { value: 'full', label: '全天' },
                  { value: 'morning', label: '早班' },
                  { value: 'afternoon', label: '午班' },
                  { value: 'evening', label: '晚班' },
                  { value: 'off', label: '休息' },
                ]}
              />;
            },
          })),
        ]}
      />
    </Card>}
    {canManage && <Card title="本周工时" style={{ marginBottom: 16 }} loading={hoursLoading} extra={<Space size={8}><Tag color="blue">总工时 {hoursData?.summary?.total_hours ?? 0} h</Tag><Button size="small" onClick={() => void loadHours()}>刷新工时</Button></Space>}>
      <Table
        rowKey="technician_id"
        size="small"
        pagination={false}
        dataSource={hoursData?.items || []}
        locale={{ emptyText: '本周暂无排班工时' }}
        columns={[
          { title: '技师', dataIndex: 'name', width: 120 },
          { title: '编码', dataIndex: 'code', width: 120 },
          { title: '出勤天数', dataIndex: 'shift_days', width: 100, align: 'right' as const },
          { title: '休息天数', dataIndex: 'off_days', width: 100, align: 'right' as const },
          { title: '请假天数', dataIndex: 'leave_days', width: 100, align: 'right' as const },
          { title: '工时', dataIndex: 'hours', width: 100, align: 'right' as const, render: (value: number) => <b>{value} h</b> },
        ]}
      />
    </Card>}
    {canManage && <Card title={`今日在岗看板${board?.date ? ` · ${board.date}` : ''}`} style={{ marginBottom: 16 }} loading={boardLoading} extra={<Button size="small" onClick={() => void loadBoard()}>刷新在岗</Button>}>
      <Space size={8} wrap>
        <Tag color="green">在岗 {board?.summary?.on_duty ?? 0}</Tag>
        <Tag color="gold">请假 {board?.summary?.on_leave ?? 0}</Tag>
        <Tag color="blue">今日预约 {board?.summary?.booking_count ?? 0}</Tag>
        <Tag>在册 {board?.summary?.total ?? 0}</Tag>
      </Space>
      <div style={{ marginTop: 12 }}>
        <Space size={8} wrap>
          {(board?.items || []).map((item: any) => <Tag
            key={item.id}
            color={item.on_leave ? 'gold' : item.status === 'busy' ? 'processing' : item.on_duty ? 'green' : 'default'}
          >{item.name} · {item.status_label}{item.booking_count ? ` · ${item.booking_count} 单` : ''}{item.next_booking_time ? ` · ${item.next_booking_time}` : ''}</Tag>)}
        </Space>
        {!board?.items?.length && <span style={{ color: 'var(--hxy-text-secondary)' }}>当前没有在册技师</span>}
      </div>
    </Card>}
    <ProTable<any> actionRef={actionRef} rowKey="id" columns={columns} search={{ labelWidth: 'auto', defaultCollapsed: true }} pagination={{ defaultPageSize: 20, showSizeChanger: true }} request={async (params) => {
      const result = await refineDataProvider.getList({ resource: resources.technicians, pagination: { currentPage: params.current, pageSize: params.pageSize, mode: 'server' }, filters: [{ field: 'status', operator: 'eq' as const, value: params.status }, { field: 'level', operator: 'eq' as const, value: params.level }], sorters: [] });
      return { success: true, data: result.data, total: result.total };
    }} options={{ density: true, fullScreen: true, reload: true, setting: true }} scroll={{ x: 780 }} />
    {canManage && <Card title="待审批请假" style={{ marginTop: 16 }} extra={<Button size="small" onClick={() => void loadLeaves()} loading={leaveLoading}>刷新</Button>}>
      <Table
        rowKey="id"
        size="small"
        loading={leaveLoading}
        dataSource={leaveRows}
        pagination={false}
        locale={{ emptyText: '没有待审批的请假申请' }}
        columns={[
          { title: '技师', dataIndex: 'technician_name', width: 120 },
          { title: '请假日期', width: 200, render: (_: any, row: any) => `${row.start_date} 至 ${row.end_date}` },
          { title: '原因', dataIndex: 'reason', ellipsis: true },
          { title: '状态', dataIndex: 'status', width: 90, render: () => <Tag color="gold">待审批</Tag> },
          { title: '操作', width: 160, render: (_: any, row: any) => <Space size={4}>
            <Button size="small" type="primary" onClick={() => void approveLeave(row)}>批准</Button>
            <Button size="small" danger onClick={() => { setRejecting(row); setRejectNote(''); }}>驳回</Button>
          </Space> },
        ]}
      />
    </Card>}
    <ModalForm title="新建技师档案" open={open} width={560} modalProps={{ destroyOnClose: true }} onOpenChange={setOpen} onFinish={async (values) => { await createTechnician({ ...values, store_id: getStoreId(staff) }); message.success('已创建技师档案'); actionRef.current?.reload(); return true; }}>
      <ProFormText name="code" label="编码" rules={[{ required: true, message: '请输入编码' }]} />
      <ProFormText name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]} />
      <ProFormText name="phone" label="手机号" />
      <ProFormSelect name="gender" label="性别" options={[{ value: '男', label: '男' }, { value: '女', label: '女' }]} />
      <ProFormSelect name="level" label="等级" initialValue="初级" options={levelOptions} />
      <ProFormDigit name="default_commission_rate" label="提成比例" initialValue={0.3} min={0} max={1} fieldProps={{ step: 0.05 }} />
    </ModalForm>
    <Modal title="驳回请假申请" open={Boolean(rejecting)} onCancel={() => setRejecting(undefined)} onOk={() => void rejectLeave()} okText="确认驳回" okButtonProps={{ danger: true, disabled: rejectNote.trim().length < 2 }}>
      <p style={{ marginTop: 0 }}>{rejecting?.technician_name} · {rejecting?.start_date} 至 {rejecting?.end_date}</p>
      <Input.TextArea rows={3} maxLength={200} showCount value={rejectNote} onChange={(event) => setRejectNote(event.target.value)} placeholder="填写驳回原因，技师端会看到" />
    </Modal>
  </PageContainer>;
}
