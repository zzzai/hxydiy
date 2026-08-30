import { useState, useEffect } from 'react';
import { App, Table, Input, Select, Button, Tag, Popconfirm } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { getUsers, getTags, addUserTag, setUserMembership } from '../api';
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
  const canCreateProfile = getStaff()?.role === 'manager' || getStaff()?.role === 'admin';

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

  const doToggleMembership = async (user: any) => {
    const next = !user.is_member;
    try {
      await setUserMembership(user.id, next);
      message.success(next ? '已开通会员（线下收款后操作）' : '已取消会员');
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败');
    }
  };

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
                <Popconfirm
                  title={r.is_member ? '确认取消该用户会员身份？' : '确认开通会员？（请先确认已线下收款）'}
                  onConfirm={() => doToggleMembership(r)}
                >
                  <Button size="small" type={r.is_member ? 'default' : 'primary'} style={{ marginLeft: 6 }}>
                    {r.is_member ? '取消会员' : '设为会员'}
                  </Button>
                </Popconfirm>
              </>
            ),
          },
        ]}
      />
      <ProfileRecordForm customerId={profileCustomerId} open={profileCustomerId !== undefined} onClose={() => setProfileCustomerId(undefined)} onSaved={() => load(page)} />
    </div>
  );
}
