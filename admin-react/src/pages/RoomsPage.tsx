import { useEffect, useMemo, useReducer, useState } from 'react';
import {
  App, Button, Descriptions, Empty, Form, Input, InputNumber, Modal, Popconfirm,
  Segmented, Select, Space, Spin, Table, Tag, Typography,
} from 'antd';
import { CheckCircleOutlined, PlusOutlined, ReloadOutlined, SettingOutlined, StopOutlined } from '@ant-design/icons';
import {
  createRoom, deleteRoom, getRooms, getRoomStats, getStaff, updateServicePositionOperationalStatus,
} from '../api';
import { canManageConfiguration } from '../auth';
import { getRoomOperationalAction, roomConfigurationReducer } from '../rooms';

type Room = {
  id: number;
  code: string;
  name: string;
  room_type: string;
  room_group?: string;
  floor?: string;
  capacity?: number;
  used_count?: number;
  current_tech?: string;
  status: string;
  operational_status?: string | null;
  parent_room_id?: number | null;
  is_space_container?: boolean;
  is_service_position?: boolean;
  bed_count?: number;
};

const STATUS_META: Record<string, { label: string; color: string; tag: string }> = {
  available: { label: '空闲', color: '#2f7d5c', tag: 'green' },
  occupied: { label: '已入座', color: '#d08a28', tag: 'gold' },
  in_service: { label: '服务中', color: '#1677ff', tag: 'blue' },
  pending_checkout: { label: '待结账', color: '#d46b08', tag: 'orange' },
  cleaning: { label: '清洁中', color: '#13a8a8', tag: 'cyan' },
  reserved: { label: '已预留', color: '#722ed1', tag: 'purple' },
  inspection: { label: '待检查', color: '#eb2f96', tag: 'magenta' },
  maintenance: { label: '维护中', color: '#cf1322', tag: 'red' },
  resting: { label: '暂停使用', color: '#7f8c8d', tag: 'default' },
  overtime_rest: { label: '超时休息', color: '#7f8c8d', tag: 'default' },
  off_duty: { label: '停用', color: '#7f8c8d', tag: 'default' },
  booked: { label: '已预约', color: '#722ed1', tag: 'purple' },
};

const GROUP_META = [
  { key: 'sofa', label: '沙发区' },
  { key: 'massage', label: '推拿区' },
  { key: 'spa', label: 'SPA 区' },
  { key: 'other', label: '其他区域' },
];

function RoomList() {
  const { message } = App.useApp();
  const [data, setData] = useState<Room[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'board' | 'config'>('board');
  const [createOpen, setCreateOpen] = useState(false);
  const [configurationRoomId, dispatchConfiguration] = useReducer(roomConfigurationReducer, null);
  const [createForm] = Form.useForm();
  const staff = getStaff();
  const canManage = canManageConfiguration(staff?.role);
  const createType = Form.useWatch('room_type', createForm) || 'sofa';
  const containerRooms = data.filter(room => room.is_space_container);

  const load = async () => {
    setLoading(true);
    try {
      const [roomsResult, statsResult] = await Promise.all([
        getRooms(), getRoomStats(),
      ]);
      setData(roomsResult.data?.items || []);
      setStats(statsResult.data || {});
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const groups = useMemo(() => GROUP_META.map(group => ({
    ...group,
    rooms: data.filter(room => (room.room_group || 'other') === group.key && room.is_space_container !== true && room.is_service_position !== false),
  })).filter(group => group.rooms.length > 0), [data]);

  const onCreate = async (values: any) => {
    if (!staff?.store_id) {
      message.error('当前账号未绑定门店，无法新建房间');
      return;
    }
    await createRoom({ ...values, store_id: staff.store_id });
    message.success('房间已创建');
    setCreateOpen(false);
    createForm.resetFields();
    await load();
  };

  const summaryItems = [
    { label: '全部房位', value: stats.total ?? data.length },
    { label: '空闲', value: stats.available || 0 },
    { label: '服务中', value: (stats.occupied || 0) + (stats.in_service || 0) },
    { label: '待结账', value: stats.pending_checkout || 0 },
    { label: '需处理', value: (stats.cleaning || 0) + (stats.inspection || 0) + (stats.maintenance || 0) },
  ];

  const board = loading ? <Spin style={{ display: 'block', margin: '72px auto' }} /> : data.length === 0 ? (
    <Empty description="暂无房间，请先在房间配置中新建" />
  ) : (
    <>
      <div className="room-summary">
        {summaryItems.map(item => (
          <div className="summary-tile" key={item.label}>
            <div className="summary-label">{item.label}</div>
            <div className="summary-value">{item.value}</div>
          </div>
        ))}
      </div>
      {groups.map(group => (
        <section className="room-section" key={group.key}>
          <div className="room-section-title"><h3>{group.label}</h3><span>{group.rooms.length} 个房位</span></div>
          <div className="room-grid">
            {group.rooms.map(room => {
              const status = STATUS_META[room.status] || { label: room.status, color: '#7f8c8d', tag: 'default' };
              return (
                <article
                  key={room.id}
                  data-testid="room-card"
                  className="room-card"
                  style={{ '--status-color': status.color } as React.CSSProperties}
                  onClick={() => dispatchConfiguration({ type: 'open', roomId: room.id })}
                >
                  <div className="room-card-head">
                    <div><div className="room-card-name">{room.name}</div><div className="room-card-code">{room.code}{room.parent_room_id ? ' · 房间内床位' : ''}</div></div>
                    <Tag color={status.tag}>{status.label}</Tag>
                  </div>
                  <div className="room-card-meta">
                    {room.current_tech ? `当前技师：${room.current_tech}` : '暂未安排技师'}
                  </div>
                  <div className="room-card-foot">
                    <span>{room.floor || '未设楼层'}</span>
                    <span>{room.used_count || 0}/{room.capacity || 1} 人</span>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </>
  );

  const config = (
    <div className="room-config-table">
      <Table
        dataSource={data}
        loading={loading}
        rowKey="id"
        size="small"
        pagination={false}
        scroll={{ x: 760 }}
        columns={[
          { title: '名称', dataIndex: 'name', render: (value, room: Room) => <Button type="link" onClick={() => dispatchConfiguration({ type: 'open', roomId: room.id })}>{value}</Button> },
          { title: '编码', dataIndex: 'code', width: 120 },
          { title: '区域', dataIndex: 'room_group', width: 100, render: (value: string) => GROUP_META.find(group => group.key === value)?.label || '其他' },
          { title: '层级', width: 130, render: (_: unknown, room: Room) => room.is_space_container ? <Tag color="blue">空间容器 · {room.bed_count || 0} 张床</Tag> : <Tag color="green">实际服务位</Tag> },
          { title: '容量', dataIndex: 'capacity', width: 80, render: (value: number) => `${value || 1} 人` },
          { title: '状态', dataIndex: 'status', width: 100, render: (value: string) => <Tag color={STATUS_META[value]?.tag}>{STATUS_META[value]?.label || value}</Tag> },
          ...(canManage ? [{ title: '操作', width: 250, render: (_: unknown, room: Room) => (
            <Space>
              <RoomOperationalToggle room={room} onChanged={load} />
              <Popconfirm title="确认删除这个房间？" onConfirm={async () => { await deleteRoom(room.id); message.success('已删除'); await load(); }}>
                <Button size="small" danger type="link">删除</Button>
              </Popconfirm>
            </Space>
          ) }] : []),
        ]}
      />
    </div>
  );

  return (
    <div>
      <div className="page-heading">
        <div><h2>房间与床位</h2><div className="page-kicker">掌握当前房态，及时完成服务流转</div></div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button>
          {view === 'config' && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建房间</Button>}
        </Space>
      </div>
      <Segmented
        value={view}
        onChange={value => setView(value as 'board' | 'config')}
        options={[
          { label: '房态看板', value: 'board' },
          ...(canManage ? [{ label: '房间配置', value: 'config', icon: <SettingOutlined /> }] : []),
        ]}
        style={{ marginBottom: 18 }}
      />
      {view === 'board' ? board : config}

      <Modal open={createOpen} onCancel={() => setCreateOpen(false)} title="新建空间或服务位" footer={null} destroyOnHidden>
        <Form form={createForm} onFinish={onCreate} layout="vertical">
          <Form.Item name="code" label="编码" rules={[{ required: true, message: '请输入编码' }]}><Input /></Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}><Input /></Form.Item>
          <Form.Item name="room_type" label="类型" initialValue="sofa">
            <Select options={[{ value: 'room', label: '房间（空间容器）' }, { value: 'sofa', label: '沙发服务位' }, { value: 'bed', label: '床位服务位' }]} />
          </Form.Item>
          {createType === 'bed' && <Form.Item name="parent_room_id" label="所属房间" rules={[{ required: true, message: '请选择床位所属房间' }]}>
            <Select placeholder="选择房间" options={containerRooms.map(room => ({ value: room.id, label: room.name }))} />
          </Form.Item>}
          <Form.Item name="is_space_container" hidden><Input /></Form.Item>
          <Form.Item name="room_group" label="区域" initialValue="sofa">
            <Select options={GROUP_META.filter(item => item.key !== 'other').map(item => ({ value: item.key, label: item.label }))} />
          </Form.Item>
          <Form.Item name="floor" label="楼层"><Input /></Form.Item>
          <Form.Item name="capacity" label="容量" initialValue={2}><InputNumber min={1} style={{ width: '100%' }} /></Form.Item>
          <Button type="primary" htmlType="submit" block onClick={() => {
            createForm.setFieldValue('is_space_container', createType === 'room');
          }}>保存</Button>
        </Form>
      </Modal>

      <Modal
        open={configurationRoomId !== null}
        onCancel={() => {
          dispatchConfiguration({ type: 'close' });
          void load();
        }}
        title="房间配置"
        footer={null}
        width={720}
        destroyOnHidden
      >
        {configurationRoomId !== null && (
          <RoomConfiguration
            roomId={configurationRoomId}
            roomSummary={data.find(room => room.id === configurationRoomId)}
            onChanged={() => void load()}
          />
        )}
      </Modal>
    </div>
  );
}

function RoomConfiguration({ roomId, roomSummary, onChanged }: { roomId: number; roomSummary?: Room; onChanged: () => void }) {
  const { message } = App.useApp();
  const [room, setRoom] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const canManage = canManageConfiguration(getStaff()?.role);

  const load = async () => {
    setLoading(true);
    try {
      setRoom(roomSummary || null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [roomId, roomSummary]);

  if (loading) return <Spin style={{ display: 'block', margin: '72px auto' }} />;
  if (!room) return <Empty description="房间不存在" />;

  return (
    <div className="room-configuration">
      <div className="room-configuration-head">
        <div>
          <div className="room-configuration-title">
            <strong>{room.name}</strong>
            <Tag color={STATUS_META[room.status]?.tag}>{STATUS_META[room.status]?.label || room.status}</Tag>
          </div>
          <div className="page-kicker">{room.code} · {GROUP_META.find(group => group.key === room.room_group)?.label || '其他区域'} · {room.floor || '未设楼层'}</div>
        </div>
        {canManage && <Space>
          <RoomOperationalToggle room={room} onChanged={onChanged} />
          <span style={{ color: '#84938f', fontSize: 12 }}>仅用于查看和房态配置</span>
        </Space>}
      </div>
      <div className="room-configuration-section">房态信息</div>
      <Descriptions column={1} size="small" items={[
        { label: '当前状态', children: STATUS_META[room.status]?.label || room.status },
        { label: '房间编码', children: room.code },
        { label: '区域', children: GROUP_META.find(group => group.key === room.room_group)?.label || '其他区域' },
      ]} />
    </div>
  );
}

function RoomOperationalToggle({ room, onChanged }: { room: Room; onChanged: () => void }) {
  const { message, modal } = App.useApp();
  const [busy, setBusy] = useState(false);
  const action = getRoomOperationalAction(room);
  if (room.is_service_position === false || room.is_space_container === true) return null;
  if (!action) {
    return room.operational_status === 'active' && room.status !== 'available'
      ? <Typography.Text type="secondary" style={{ fontSize: 12 }}>有活动占用</Typography.Text>
      : null;
  }
  const disabling = action === 'disable';
  const nextStatus = disabling ? 'inactive' : 'active';
  const run = () => {
    modal.confirm({
      title: `${disabling ? '停用' : '重新启用'}${room.name}？`,
      content: disabling
        ? '停用后将拒绝新的顾客扫码和共享 iPad 入口；不会操作智慧宝的沙发、房间或清洁状态。'
        : '重新启用后将恢复顾客扫码和共享 iPad 入口；不会操作智慧宝的物理资源。',
      okText: disabling ? '确认停用' : '确认启用',
      okButtonProps: disabling ? { danger: true } : undefined,
      cancelText: '返回',
      onOk: async () => {
        setBusy(true);
        try {
          await updateServicePositionOperationalStatus(
            room.id,
            nextStatus,
            disabling ? '房间配置页停用服务位' : '房间配置页重新启用服务位',
          );
          message.success(disabling ? '服务位已停用' : '服务位已重新启用');
          onChanged();
        } finally {
          setBusy(false);
        }
      },
    });
  };
  return <Button
    size="small"
    type={disabling ? 'link' : 'link'}
    danger={disabling}
    icon={disabling ? <StopOutlined /> : <CheckCircleOutlined />}
    loading={busy}
    onClick={run}
  >{disabling ? '停用服务位' : '重新启用服务位'}</Button>;
}

export default function RoomsPage() {
  return <RoomList />;
}
