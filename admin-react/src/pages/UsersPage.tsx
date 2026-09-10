import { useState, useEffect } from 'react';
import { App, Table, Input, Select, Button, Tag, Popconfirm, Modal, Descriptions, Form, Checkbox } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { getUsers, getTags, addUserTag, enrollAnnualMembership, renewAnnualMembership, cancelAnnualMembership, recoverAnnualMembership, getCustomerTrustedDevice, revokeCustomerTrustedDevice } from '../api';
import { getStaff } from '../api';
import ProfileRecordForm from '../features/technician/ProfileRecordForm';

export default function UsersPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [tagFilter, setTagFilter] = useState<number | undefined>();
  const [memberFilter, setMemberFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [tags, setTags] = useState<any[]>([]);
  const [profileCustomerId, setProfileCustomerId] = useState<number>();
  const [deviceCustomer, setDeviceCustomer] = useState<any>();
  const [deviceState, setDeviceState] = useState<any>();
  const [membershipCustomer, setMembershipCustomer] = useState<any>();
  const [membershipMode, setMembershipMode] = useState<'enroll' | 'renew' | 'cancel' | 'recover'>('enroll');
  const [membershipForm] = Form.useForm();
  const canCreateProfile = getStaff()?.role === 'manager' || getStaff()?.role === 'admin';
  const canManageDevice = getStaff()?.role === 'manager';

  useEffect(() => { getTags().then(r => setTags(r.data || [])); }, []);

  const load = async (p = 1) => {
    setLoading(true);
    const params: any = { page: p, page_size: 30 };
    if (search) params.search = search;
    if (tagFilter) params.tag_id = tagFilter;
    if (memberFilter) params.is_member = memberFilter;
    try { const r = await getUsers(params); setData(r.data?.items || []); setTotal(r.data?.total || 0); } catch {} finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [tagFilter, memberFilter]);

  const doAddTag = async (userId: number) => {
    const tagId = prompt('输入标签 ID: ' + tags.map((t: any) => `[${t.id}] ${t.name}`).join(', '));
    if (!tagId) return;
    await addUserTag(userId, Number(tagId));
    message.success('已打标'); load();
  };

  const openMembership = (user: any, mode: 'enroll' | 'renew' | 'cancel' | 'recover') => {
    setMembershipCustomer(user);
    setMembershipMode(mode);
    membershipForm.setFieldsValue({
      payment_channel: 'cash',
      rights_confirmed: false,
      refund_disposition: 'refunded',
      cycle_id: user.membership_cycle_id,
    });
  };
  const submitMembership = async () => {
    if (!membershipCustomer) return;
    try {
      const values = await membershipForm.validateFields();
      if (membershipMode === 'enroll') await enrollAnnualMembership(membershipCustomer.id, values);
      if (membershipMode === 'renew') await renewAnnualMembership(membershipCustomer.id, values);
      if (membershipMode === 'cancel') await cancelAnnualMembership(membershipCustomer.id, values);
      if (membershipMode === 'recover') await recoverAnnualMembership(membershipCustomer.id, values);
      message.success(membershipMode === 'cancel' ? '会员周期已取消，未用赠送权益已作废' : '会员周期操作已完成');
      setMembershipCustomer(undefined);
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败');
    }
  };
  const openDevice = async (user: any) => { setDeviceCustomer(user); const response = await getCustomerTrustedDevice(user.id); setDeviceState(response.data); };
  const revokeDevice = async () => { if (!deviceCustomer) return; await revokeCustomerTrustedDevice(deviceCustomer.id, '顾客申请换机，店长确认撤销旧设备'); message.success('旧可信设备和未使用会员码已撤销'); const response = await getCustomerTrustedDevice(deviceCustomer.id); setDeviceState(response.data); };

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <Input prefix={<SearchOutlined />} placeholder="搜索昵称或手机号" value={search} onChange={e => setSearch(e.target.value)} onPressEnter={() => load()} style={{ width: 200 }} />
        <Select placeholder="全部标签" allowClear value={tagFilter} onChange={setTagFilter} style={{ width: 160 }} options={tags.map((t: any) => ({ value: t.id, label: t.name }))} />
        <Select placeholder="全部身份" allowClear value={memberFilter} onChange={setMemberFilter} style={{ width: 120 }} options={[{ value: '1', label: '会员' }, { value: '0', label: '非会员' }]} />
        <Button type="primary" onClick={() => load()}>搜索</Button>
      </div>
      <Table dataSource={data} loading={loading} rowKey="id" size="small"
        pagination={{ current: page, total, pageSize: 30, onChange: (p) => { setPage(p); load(p); } }}
        columns={[
          { title: '用户', dataIndex: 'nickname', render: (v: string, r: any) => <>{v} {r.is_member && <Tag color="gold">会员</Tag>}</> },
          { title: '手机号', dataIndex: 'phone_masked', width: 130 },
          { title: '余额', dataIndex: 'balance_cents', width: 100, render: (v: number) => `¥${(v / 100).toFixed(2)}` },
          { title: '标签', width: 240, render: (_: any, r: any) => (r.tags || []).map((t: any) => <Tag key={t.id} color={t.color}>{t.name}</Tag>) },
          { title: '注册时间', dataIndex: 'created_at', width: 140, render: (v: string) => v?.slice(0, 10) },
          {
            title: '操作', width: 170,
            render: (_: any, r: any) => (
              <>
                <Button size="small" onClick={() => doAddTag(r.id)}>打标</Button>
                {canCreateProfile && <Button size="small" style={{ marginLeft: 6 }} onClick={() => setProfileCustomerId(r.id)}>画像记录</Button>}
                {r.is_member && canManageDevice && <Button size="small" style={{ marginLeft: 6 }} onClick={() => void openDevice(r)}>可信设备</Button>}
                {r.is_member ? <>
                  <Button size="small" style={{ marginLeft: 6 }} onClick={() => openMembership(r, 'renew')}>续费</Button>
                  <Popconfirm title="确认取消/退款？未使用年度赠送权益会作废，已核销权益不会回退。" onConfirm={() => openMembership(r, 'cancel')}>
                    <Button size="small" danger style={{ marginLeft: 6 }}>取消/退款</Button>
                  </Popconfirm>
                </> : <>
                  <Button size="small" type="primary" style={{ marginLeft: 6 }} onClick={() => openMembership(r, 'enroll')}>办理会员</Button>
                  {r.membership_cycle_id && <Button size="small" style={{ marginLeft: 6 }} onClick={() => openMembership(r, 'recover')}>异常恢复</Button>}
                </>}
              </>
            ),
          },
        ]}
      />
      <ProfileRecordForm customerId={profileCustomerId} open={profileCustomerId !== undefined} onClose={() => setProfileCustomerId(undefined)} onSaved={() => load(page)} />
      <Modal title={{ enroll: '办理年度会员', renew: '续费年度会员', cancel: '取消/退款年度会员', recover: '异常恢复会员周期' }[membershipMode]} open={Boolean(membershipCustomer)} onCancel={() => setMembershipCustomer(undefined)} onOk={() => void submitMembership()} okText="确认提交" destroyOnClose>
        <p>{membershipCustomer?.nickname || membershipCustomer?.phone_masked || '顾客'}{membershipCustomer?.member_expire_at ? `，当前到期：${membershipCustomer.member_expire_at.slice(0, 10)}` : ''}</p>
        <Form form={membershipForm} layout="vertical">
          {(membershipMode === 'enroll' || membershipMode === 'renew') && <>
            <Form.Item name="payment_channel" label="支付渠道" rules={[{ required: true, message: '请选择支付渠道' }]}><Select options={[{ value: 'cash', label: '现金' }, { value: 'wechat', label: '微信支付' }, { value: 'alipay', label: '支付宝' }, { value: 'manual_receipt', label: '人工收据' }]} /></Form.Item>
            <Form.Item name="payment_reference" label="流水尾号或人工收据号" rules={[{ required: true, min: 2, message: '请填写至少 2 位凭据' }]}><Input maxLength={64} /></Form.Item>
            <Form.Item name="rights_confirmed" valuePropName="checked" rules={[{ validator: (_rule, value) => value ? Promise.resolve() : Promise.reject(new Error('请确认已说明会员权益')) }]}><Checkbox>已向顾客说明并确认会员权益</Checkbox></Form.Item>
          </>}
          {(membershipMode === 'cancel' || membershipMode === 'recover') && <>
            <Form.Item name="cycle_id" hidden rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="reason" label="原因" rules={[{ required: true, min: 2, message: '请填写原因' }]}><Input.TextArea maxLength={200} /></Form.Item>
          </>}
          {membershipMode === 'cancel' && <Form.Item name="refund_disposition" label="退款处置" rules={[{ required: true, message: '请选择退款处置' }]}><Select options={[{ value: 'refunded', label: '已退款' }, { value: 'cancelled_before_payment', label: '收款前取消' }, { value: 'other', label: '其他已登记处置' }]} /></Form.Item>}
          {membershipMode === 'recover' && <Form.Item name="idempotency_key" label="异常恢复编号" rules={[{ required: true, min: 1, message: '请填写可追溯编号' }]}><Input maxLength={64} placeholder="例如：recover-20260910-001" /></Form.Item>}
        </Form>
        <p>日常会员核验请使用技师端扫码；电脑后台不能通过手机号直接给予会员价。</p>
      </Modal>
      <Modal title="会员可信设备" open={Boolean(deviceCustomer)} onCancel={() => { setDeviceCustomer(undefined); setDeviceState(undefined); }} footer={deviceState?.bound ? <Popconfirm title="确认已核实顾客换机申请？撤销后旧设备和旧会员码立即失效。" onConfirm={() => void revokeDevice()}><Button danger>撤销旧设备</Button></Popconfirm> : null}><Descriptions column={1} items={[{ label: '会员', children: deviceCustomer?.nickname || deviceCustomer?.phone_masked || '-' }, { label: '设备状态', children: deviceState?.bound ? <Tag color="green">已绑定</Tag> : <Tag>未绑定</Tag> }, { label: '绑定时间', children: deviceState?.created_at?.slice(0, 19) || '-' }, { label: '最近使用', children: deviceState?.last_seen_at?.slice(0, 19) || '-' }]} /><p>管理后台只处理受控换绑与审计，日常会员核验请使用技师端扫码。</p></Modal>
    </div>
  );
}
