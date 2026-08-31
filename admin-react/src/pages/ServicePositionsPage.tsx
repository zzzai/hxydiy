import { useEffect, useMemo, useState } from 'react';
import QRCode from 'qrcode';
import {
  Alert,
  App,
  Button,
  Descriptions,
  Divider,
  Empty,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CoffeeOutlined,
  CopyOutlined,
  ExportOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  StopOutlined,
  SwapOutlined,
  TabletOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  createKioskSession,
  finishPositionService,
  getLiveServicePositionMap,
  getPositionQrLink,
  getStaff,
  rebindPositionQr,
  regeneratePositionQr,
  startPositionService,
  updateServicePositionOperationalStatus,
  updatePositionQr,
  type PositionQr,
} from '../api';
import { makeIdempotencyKey } from '../operations';
import {
  POSITION_ACTION_LABELS,
  buildKioskUrl,
  countPositionStates,
  getPositionActions,
  getServicePositionOperationalAction,
  occupancyStatusMeta,
  positionTypeLabel,
  splitPositionGroups,
  waitingReleaseMeta,
  normalizeServicePositions,
  type PositionAction,
  type ServicePosition,
} from '../servicePositions';
import { canManageConfiguration } from '../auth';
import { getServicePositionQrPermissions, servicePositionQrActions, servicePositionQrRenderOptions } from '../servicePositionQr';

type ActionMode = 'start_service' | 'kiosk' | null;

const dateTime = (value?: string | null) => value
  ? new Date(value).toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '-';
const sourceText = (value?: string) => value === 'kiosk'
  ? '共享 iPad'
  : value === 'room_qr'
    ? '房间二维码'
    : value === 'bound_qr'
      ? '绑定二维码'
    : value === 'personal_qr'
      ? '顾客手机扫码'
      : value || '-';

function elapsedText(value: string | null | undefined, now: number, future = false) {
  if (!value) return '-';
  const seconds = Math.max(0, Math.floor((future ? new Date(value).getTime() - now : now - new Date(value).getTime()) / 1000));
  if (seconds < 60) return future ? `${seconds} 秒后` : '刚刚';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return future ? `${minutes} 分钟后` : `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${hours} 小时${rest ? ` ${rest} 分钟` : ''}`;
}

function PositionTile({ position, now, onClick }: { position: ServicePosition; now: number; onClick: () => void }) {
  const meta = occupancyStatusMeta(position.state);
  const occupancy = position.occupancy;
  const overrun = position.state === 'in_service' && occupancy?.expected_end_at
    && new Date(occupancy.expected_end_at).getTime() < now;
  const expiring = position.state === 'held' && occupancy?.hold_expires_at
    && new Date(occupancy.hold_expires_at).getTime() - now < 2 * 60 * 1000;
  const waiting = occupancy && position.state === 'waiting_service'
    ? waitingReleaseMeta(occupancy, position.selection?.status, position.selection?.submitted_at, now)
    : null;
  const waitingLabel = waiting?.level === 'overdue'
    ? '等待已超时'
    : waiting?.level === 'urgent'
      ? '即将释放'
      : waiting?.level === 'warning'
        ? '等待较久'
        : null;
  const statusLabel = overrun ? '服务超时·有人' : expiring ? '占位即将到期' : waitingLabel || meta.label;
  const timing = position.state === 'held'
    ? elapsedText(occupancy?.hold_expires_at, now, true)
    : waiting?.dueAt && waiting.level !== 'confirmed'
      ? waiting.remainingMs !== null && waiting.remainingMs <= 0
        ? `已超 ${elapsedText(waiting.dueAt, now)}`
        : `${elapsedText(waiting.dueAt, now, true)}释放`
    : position.state === 'in_service' && occupancy?.expected_end_at
      ? overrun ? `已超 ${elapsedText(occupancy.expected_end_at, now)}` : `${elapsedText(occupancy.expected_end_at, now, true)}结束`
      : position.selection?.submitted_at ? `等待 ${elapsedText(position.selection.submitted_at, now)}` : '';
  return (
    <button
      type="button"
      className={`live-position state-${meta.tone} ${overrun || expiring || ['urgent', 'overdue'].includes(waiting?.level || '') ? 'state-urgent' : ''} ${waiting?.level === 'warning' ? 'state-warning' : ''}`}
      style={{
        '--position-color': meta.color,
      } as React.CSSProperties}
      onClick={onClick}
      aria-label={`${position.name}，${statusLabel}`}
    >
      <span className="position-tile-head"><strong>{position.name}</strong><i /></span>
      <span className="position-type-label">{positionTypeLabel(position.type)}</span>
      <span className="position-state-label">{statusLabel}</span>
      {timing && <small><ClockCircleOutlined /> {timing}</small>}
    </button>
  );
}

export default function ServicePositionsPage() {
  const { message, modal } = App.useApp();
  const staff = getStaff();
  const qrPermissions = getServicePositionQrPermissions(staff?.role);
  const canManageServicePosition = canManageConfiguration(staff?.role);
  const [positions, setPositions] = useState<ServicePosition[]>([]);
  const [updatedAt, setUpdatedAt] = useState('');
  const [selected, setSelected] = useState<ServicePosition | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [actionMode, setActionMode] = useState<ActionMode>(null);
  const [expectedMinutes, setExpectedMinutes] = useState(60);
  const [deviceLabel, setDeviceLabel] = useState('前台共享 iPad');
  const [kioskLink, setKioskLink] = useState('');
  const [positionQrLink, setPositionQrLink] = useState('');
  const [positionQrImage, setPositionQrImage] = useState('');
  const [positionQr, setPositionQr] = useState<PositionQr | null>(null);
  const [qrTargetRoomId, setQrTargetRoomId] = useState<number>();
  const [qrBusy, setQrBusy] = useState(false);
  const [positionConfigBusy, setPositionConfigBusy] = useState(false);

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const response = await getLiveServicePositionMap();
      setPositions(normalizeServicePositions(response.data.positions));
      setUpdatedAt(response.data.updated_at);
      setSelected((current) => current
        ? response.data.positions.find((position) => position.id === current.id) || null
        : null);
    } catch {
      if (!silent) message.error('服务位状态加载失败');
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const poller = window.setInterval(() => void load(true), 3000);
    const ticker = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.clearInterval(poller);
      window.clearInterval(ticker);
    };
  }, []);


  const counts = useMemo(() => countPositionStates(positions), [positions]);
  const positionGroups = useMemo(() => splitPositionGroups(positions), [positions]);
  const availableTargets = positions.filter((position) => position.state === 'available' && position.operational_status === 'active');
  const actions = selected?.occupancy
    ? getPositionActions(
      selected.state,
      staff?.role,
      Boolean(selected.selection?.fulfillment_order_id),
      selected.selection?.service_order_status,
      selected.state === 'cleaning' && Boolean(selected.occupancy?.release_reason),
      selected.selection?.status,
    )
    : [];

  const closeDetail = () => {
    setSelected(null);
    setActionMode(null);
    setKioskLink('');
    setPositionQr(null);
    setPositionQrLink('');
    setPositionQrImage('');
    setQrTargetRoomId(undefined);
  };

  const runAction = async (action: Exclude<PositionAction, 'move' | 'force_release' | 'retain'>) => {
    if (!selected?.occupancy) return;
    const occupancyId = selected.occupancy.id;
    const copy: Record<string, string> = {
      start_service: '开始后将记录实际开始时间，并按预计时长提醒。',
      finish_service: '记录服务结束；智慧宝负责实际开关沙发，DIY 不再提供离位或清洁按钮。',
    };
    modal.confirm({
      title: `${POSITION_ACTION_LABELS[action]}？`,
      content: copy[action],
      okText: POSITION_ACTION_LABELS[action],
      cancelText: '返回',
      onOk: async () => {
        setActing(true);
        try {
          if (action === 'start_service') await startPositionService(occupancyId, expectedMinutes);
          if (action === 'finish_service') await finishPositionService(occupancyId);
          message.success(`${POSITION_ACTION_LABELS[action]}已记录`);
          setActionMode(null);
          await load(true);
        } finally {
          setActing(false);
        }
      },
    });
  };

  const bindKiosk = async () => {
    if (!selected || selected.state !== 'available') return;
    setActing(true);
    try {
      const response = await createKioskSession(selected.id, deviceLabel.trim() || '共享 iPad');
      const base = import.meta.env.VITE_DIY_BASE_URL
        || `${window.location.protocol}//${window.location.hostname}:4180/diy/`;
      const link = buildKioskUrl(base, response.data.session.store_id, response.data.session.id, response.data.access_token);
      setKioskLink(link);
      message.success('共享 iPad 已绑定当前服务位');
      await load(true);
    } finally {
      setActing(false);
    }
  };

  const copyPositionQrLink = async () => {
    if (!selected) return;
    try {
      const response = await getPositionQrLink(selected.id);
      setPositionQr(response.data);
      setPositionQrLink(response.data.url);
      setPositionQrImage(await QRCode.toDataURL(response.data.url, servicePositionQrRenderOptions));
      if (response.data.status === 'active') {
        await navigator.clipboard.writeText(response.data.url);
        message.success(`${selected.name}二维码链接已复制`);
      } else {
        message.warning(`${selected.name}二维码当前已停用`);
      }
    } catch { /* 全局拦截器已提示 */ }
  };

  const applyQr = async (qr: PositionQr, success: string) => {
    setPositionQr(qr);
    setPositionQrLink(qr.url);
    setPositionQrImage(await QRCode.toDataURL(qr.url, servicePositionQrRenderOptions));
    setQrTargetRoomId(undefined);
    message.success(success);
  };

  const changeQrStatus = async (status: 'active' | 'disabled') => {
    if (!positionQr) return;
    setQrBusy(true);
    try {
      const response = await updatePositionQr(
        positionQr.qr_id,
        status,
        status === 'disabled' ? '门店管理员停用现场二维码' : '门店管理员重新启用现场二维码',
      );
      await applyQr(response.data, status === 'disabled' ? '二维码已停用，旧码不可继续使用' : '二维码已重新启用');
    } finally {
      setQrBusy(false);
    }
  };

  const confirmRegenerateQr = () => {
    if (!positionQr) return;
    modal.confirm({
      title: '重新生成二维码？',
      content: '旧二维码会立即失效。请下载新二维码并替换现场贴码。',
      okText: '生成新二维码',
      cancelText: '返回',
      onOk: async () => {
        const response = await regeneratePositionQr(positionQr.qr_id, '现场二维码重新印制');
        await applyQr(response.data, '新二维码已生成，请及时替换现场旧码');
      },
    });
  };

  const confirmRebindQr = () => {
    if (!positionQr || !qrTargetRoomId) return;
    const target = positions.find((item) => item.id === qrTargetRoomId);
    modal.confirm({
      title: `换绑到${target?.name || '目标服务位'}？`,
      content: '系统会停用当前二维码并生成一个绑定目标服务位的新二维码，不会改变历史到店记录。',
      okText: '确认换绑',
      cancelText: '返回',
      onOk: async () => {
        const response = await rebindPositionQr(positionQr.qr_id, qrTargetRoomId, '现场二维码调整绑定位置');
        await applyQr(response.data, `已生成绑定${target?.name || '目标服务位'}的新二维码`);
      },
    });
  };

  const confirmServicePositionOperationalStatus = () => {
    if (!selected) return;
    const action = getServicePositionOperationalAction(selected.operational_status, Boolean(selected.occupancy));
    if (!action) return;
    const disabling = action === 'disable';
    modal.confirm({
      title: `${disabling ? '停用' : '重新启用'}${selected.name}？`,
      content: disabling
        ? '停用后，DIY 将拒绝新的顾客扫码和共享 iPad 入口；不会操作智慧宝的沙发、房间或清洁状态。已有顾客时不能停用。'
        : '重新启用后，服务位可再次接收顾客扫码和共享 iPad 入口；不会操作智慧宝的物理资源。',
      okText: disabling ? '确认停用' : '确认启用',
      okButtonProps: disabling ? { danger: true } : undefined,
      cancelText: '返回',
      onOk: async () => {
        setPositionConfigBusy(true);
        try {
          await updateServicePositionOperationalStatus(
            selected.id,
            disabling ? 'inactive' : 'active',
            disabling ? '店长停用服务位' : '店长重新启用服务位',
          );
          message.success(disabling ? '服务位已停用，不再接收新的扫码入口' : '服务位已重新启用');
          await load(true);
        } finally {
          setPositionConfigBusy(false);
        }
      },
    });
  };

  const downloadPositionQr = () => {
    if (!selected || !positionQrImage) return;
    const link = document.createElement('a');
    link.href = positionQrImage;
    link.download = `荷小悦-${selected.code}-顾客二维码.png`;
    link.click();
  };

  const copyKioskLink = async () => {
    await navigator.clipboard.writeText(kioskLink);
    message.success('试用链接已复制');
  };

  const detailMeta = selected
    ? selected.operational_status !== 'active'
      ? { label: '已停用', color: '#84928e', tone: 'muted' as const, description: 'DIY 已暂停新的顾客扫码和共享 iPad 入口。' }
      : occupancyStatusMeta(selected.state)
    : null;
  const selectionItems = selected?.selection?.items || [];
  const detailWaiting = selected?.occupancy && selected.state === 'waiting_service'
    ? waitingReleaseMeta(selected.occupancy, selected.selection?.status, selected.selection?.submitted_at, now)
    : null;

  return (
    <div className="service-position-page">
      <div className="page-heading position-page-heading">
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>服务位看板</Typography.Title>
          <Typography.Text type="secondary">扫码占位、项目提交、服务、离位和清洁的实时现场状态</Typography.Text>
        </div>
        <Space>
          <Typography.Text type="secondary" className="live-updated">3 秒自动刷新 · {updatedAt ? dateTime(updatedAt) : '-'}</Typography.Text>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button>
        </Space>
      </div>

      <div className="position-stats" aria-label="服务位状态统计">
        {[
          ['可用', counts.available, 'available'],
          ['选单中', counts.held, 'held'],
          ['待服务', counts.waiting_service, 'waiting'],
          ['服务中', counts.in_service, 'serving'],
          ['需处理', counts.attention, 'attention'],
        ].map(([label, value, tone]) => (
          <div className={`position-stat stat-${tone}`} key={String(label)}><span>{label}</span><strong>{value}</strong></div>
        ))}
      </div>

      <div className="position-workspace">
        <section className="live-map-section">
          <header className="live-map-header">
            <div><strong>全店服务位</strong><span>点击服务位直接处理，不跳转页面</span></div>
            <div className="position-legend">
              <span><i className="legend-available" />可用</span>
              <span><i className="legend-active" />服务中</span>
              <span><i className="legend-attention" />需处理</span>
            </div>
          </header>
          <div className="position-groups" aria-label="全店服务位列表">
            <section className="position-group" aria-labelledby="sofa-group-title">
              <header><strong id="sofa-group-title">大厅沙发</strong><span>{positionGroups.sofas.length} 个</span></header>
              <div className="position-grid sofa-grid">
                {positionGroups.sofas.map((position) => (
                  <PositionTile key={position.id} position={position} now={now} onClick={() => { setSelected(position); setActionMode(null); setKioskLink(''); setPositionQr(null); setPositionQrLink(''); setPositionQrImage(''); }} />
                ))}
              </div>
            </section>
            <section className="position-group" aria-labelledby="room-group-title">
              <header><strong id="room-group-title">房间床位</strong><span>{positionGroups.rooms.length} 个</span></header>
              <div className="position-grid room-position-grid">
                {positionGroups.rooms.map((position) => (
                  <PositionTile key={position.id} position={position} now={now} onClick={() => { setSelected(position); setActionMode(null); setKioskLink(''); setPositionQr(null); setPositionQrLink(''); setPositionQrImage(''); }} />
                ))}
              </div>
            </section>
          </div>
        </section>

        <aside className="position-side-panel">
          <div className="side-panel-title"><strong>现场提醒</strong><span>{counts.held + counts.waiting_service + counts.attention} 项</span></div>
          <div className="attention-list">
            {positions.filter((position) => ['held', 'waiting_service', 'post_service_present', 'cleaning'].includes(position.state)).map((position) => {
              const meta = occupancyStatusMeta(position.state);
              return <button type="button" key={position.id} onClick={() => { setSelected(position); setPositionQr(null); setPositionQrLink(''); setPositionQrImage(''); }}><i style={{ background: meta.color }} /><span><strong>{position.name}</strong><small>{meta.label}</small></span><b>查看</b></button>;
            })}
            {!positions.some((position) => ['held', 'waiting_service', 'post_service_present', 'cleaning'].includes(position.state)) && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待处理事项" />}
          </div>
          <div className="position-rule-note"><WarningOutlined /><span><strong>智慧宝负责沙发开关</strong><small>DIY 仅记录确认服务和服务结束；项目预计结束后超过 30 分钟未结束时，系统自动关闭本次 DIY 占用并记录审计。</small></span></div>
        </aside>
      </div>

      <Modal
        open={Boolean(selected)}
        title={null}
        footer={null}
        width={760}
            destroyOnHidden
        onCancel={closeDetail}
        className="position-detail-modal"
      >
        {selected && detailMeta && (
          <div className="position-detail">
            <header className="position-detail-head">
              <div><span className="position-detail-kicker">{positionTypeLabel(selected.type)}</span><Typography.Title level={3}>{selected.name}</Typography.Title></div>
              <Tag color={detailMeta.color}>{detailMeta.label}</Tag>
            </header>
            <Alert type="info" showIcon={false} message={detailMeta.description} className="position-detail-alert" />
            {detailWaiting && <Alert
              type={detailWaiting.level === 'overdue' || detailWaiting.level === 'urgent' ? 'warning' : 'info'}
              showIcon
              message={detailWaiting.label}
              description={detailWaiting.dueAt ? `当前截止时间：${dateTime(detailWaiting.dueAt)}` : undefined}
              className="position-waiting-alert"
            />}

            {selected.operational_status !== 'active' ? (
              <div className="available-position-state"><StopOutlined /><div><strong>服务位已停用</strong><span>DIY 不再接收新的顾客扫码或共享 iPad 入口；不会影响智慧宝物理资源。</span></div></div>
            ) : selected.occupancy ? (
              <>
                <Descriptions
                  column={{ xs: 1, sm: 2 }}
                  size="small"
                  className="position-descriptions"
                  items={[
                    { label: '顾客入口', children: sourceText(selected.occupancy.source) },
                    { label: '设备', children: selected.selection?.device_label || '-' },
                    { label: '选单状态', children: selected.selection?.status || '草稿' },
                    { label: '选单提交', children: dateTime(selected.selection?.submitted_at) },
                    { label: '开始服务', children: dateTime(selected.occupancy.actual_start_at) },
                    { label: '预计结束', children: dateTime(selected.occupancy.expected_end_at) },
                  ]}
                />
                <Divider />
                <div className="selection-detail-head"><strong>顾客选择</strong><span>{selectionItems.length} 项</span></div>
                <div className="selection-item-list">
                  {selectionItems.map((item, index) => (
                    <div className="selection-item" key={`${item.project_id}-${index}`}>
                      <span className={item.item_type === 'preference' ? 'tea-item-icon' : ''}>{item.item_type === 'preference' ? <CoffeeOutlined /> : index + 1}</span>
                      <div><strong>{item.name || '服务项目'}</strong><small>{item.diy_preferences?.join(' · ') || '按标准流程服务'}</small></div>
                      {item.item_type === 'preference' && <Tag>赠饮</Tag>}
                    </div>
                  ))}
                  {!selectionItems.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="顾客尚未选择项目" />}
                </div>
              </>
            ) : (
              <div className="available-position-state"><CheckCircleOutlined /><div><strong>当前可接待</strong><span>可由顾客扫码进入，也可先绑定共享 iPad。</span></div></div>
            )}

            <Divider />
            <div className="position-actions">
              <div className="position-actions-title"><strong>现场操作</strong><span>系统会记录每次状态变更</span></div>
              <Space wrap>
                {actions.includes('start_service') && <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setActionMode('start_service')}>确认服务</Button>}
                {actions.includes('finish_service') && <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => void runAction('finish_service')}>服务结束</Button>}
                {qrPermissions.canView && <Button icon={<CopyOutlined />} onClick={() => void copyPositionQrLink()}>查看顾客二维码</Button>}
                {canManageServicePosition && getServicePositionOperationalAction(selected.operational_status, Boolean(selected.occupancy)) === 'disable' && <Button danger icon={<StopOutlined />} loading={positionConfigBusy} onClick={confirmServicePositionOperationalStatus}>停用服务位</Button>}
                {canManageServicePosition && getServicePositionOperationalAction(selected.operational_status, Boolean(selected.occupancy)) === 'enable' && <Button type="primary" icon={<CheckCircleOutlined />} loading={positionConfigBusy} onClick={confirmServicePositionOperationalStatus}>重新启用服务位</Button>}
                {selected.state === 'available' && <>
                  <Button type="primary" icon={<TabletOutlined />} onClick={() => setActionMode('kiosk')}>绑定共享 iPad</Button>
                </>}
              </Space>
            </div>

            {actionMode === 'start_service' && (
              <div className="inline-action-panel">
                <div><strong>预计服务时长</strong><span>到时仅提醒，不会自动结束或释放服务位。</span></div>
                <Space align="center"><InputNumber min={10} max={480} value={expectedMinutes} onChange={(value) => setExpectedMinutes(value || 60)} addonAfter="分钟" /><Button type="primary" loading={acting} onClick={() => void runAction('start_service')}>确认开始</Button><Button onClick={() => setActionMode(null)}>取消</Button></Space>
              </div>
            )}

            {actionMode === 'kiosk' && (
              <div className="inline-action-panel kiosk-panel">
                <div><strong>前台绑定共享 iPad</strong><span>绑定后该服务位立即进入 10 分钟临时占用，请在对应设备打开链接。</span></div>
                {!kioskLink ? (
                  <><Input value={deviceLabel} onChange={(event) => setDeviceLabel(event.target.value)} maxLength={64} prefix={<TabletOutlined />} /><Space><Button type="primary" loading={acting} onClick={() => void bindKiosk()}>生成顾客选项目页面</Button><Button onClick={() => setActionMode(null)}>取消</Button></Space></>
                ) : (
                  <div className="kiosk-link-result">
                    <Alert type="success" showIcon message="当前服务位已绑定" description="一次性凭证会在顾客页面接管后从地址栏移除。" />
                    <Input value={kioskLink} readOnly suffix={<Tooltip title="复制链接"><Button type="text" icon={<CopyOutlined />} onClick={() => void copyKioskLink()} /></Tooltip>} />
                    <Space><Button type="primary" icon={<ExportOutlined />} onClick={() => window.open(kioskLink, '_blank', 'noopener,noreferrer')}>在此设备打开</Button><Button icon={<CopyOutlined />} onClick={() => void copyKioskLink()}>复制链接</Button></Space>
                  </div>
                )}
              </div>
            )}
            {positionQrLink && selected && positionQr && (
              <Alert type={positionQr.status === 'active' ? 'success' : 'warning'} showIcon closable onClose={() => { setPositionQrLink(''); setPositionQrImage(''); setPositionQr(null); }}
                message={`${selected.name}二维码 · ${positionQr.status === 'active' ? '使用中' : '已停用'}`}
                description={<Space direction="vertical">
                  {positionQr.status === 'active' && positionQrImage && <img src={positionQrImage} alt={`${selected.name}顾客二维码`} style={{ width: 220, maxWidth: '100%' }} />}
                  {positionQr.status === 'active'
                    ? <Typography.Text copyable={{ text: positionQrLink }}>{positionQrLink}</Typography.Text>
                    : <Typography.Text type="secondary">该二维码已失效，不再展示或提供下载。重新启用，或生成新二维码后再打印投放。</Typography.Text>}
                  <Typography.Text type="secondary">二维码只绑定当前门店和具体服务位；停用或换绑后旧码立即失效。</Typography.Text>
                  <Space wrap>
                    {qrPermissions.canManage && servicePositionQrActions(positionQr.status, false).includes('disable') && <Button danger icon={<StopOutlined />} loading={qrBusy} onClick={() => void changeQrStatus('disabled')}>停用二维码</Button>}
                    {qrPermissions.canManage && servicePositionQrActions(positionQr.status, false).includes('enable') && <Button type="primary" loading={qrBusy} onClick={() => void changeQrStatus('active')}>重新启用</Button>}
                    {positionQr.status === 'active' && <Button type="primary" onClick={downloadPositionQr}>下载打印二维码</Button>}
                    {qrPermissions.canManage && (!positionQr.status || positionQr.status === 'active' ? <Button onClick={confirmRegenerateQr}>重新生成</Button> : <Button onClick={confirmRegenerateQr}>生成新二维码</Button>)}
                  </Space>
                  {qrPermissions.canManage && <Space wrap>
                      <Select
                        value={qrTargetRoomId}
                        onChange={setQrTargetRoomId}
                        placeholder="选择换绑目标服务位"
                        style={{ minWidth: 220 }}
                        options={availableTargets.filter((item) => item.id !== selected.id).map((item) => ({ value: item.id, label: item.name }))}
                      />
                      <Button icon={<SwapOutlined />} disabled={!qrTargetRoomId} onClick={confirmRebindQr}>换绑服务位</Button>
                    </Space>}
                </Space>}
              />
            )}
          </div>
        )}
      </Modal>

    </div>
  );
}
