import { DoorClosed, LocateFixed, Sofa, X } from 'lucide-react';
import { useEffect } from 'react';

import type { ServicePosition } from '../api';
import { getPositionSelectionDecision } from '../positionSelection';

type Props = {
  open: boolean;
  current: ServicePosition | null;
  positions: ServicePosition[];
  moving: boolean;
  source: string;
  onClose: () => void;
  onSelect: (position: ServicePosition) => void;
  onBlocked: (message: string) => void;
};

export default function SeatMapDialog({ open, current, positions, moving, source, onClose, onSelect, onBlocked }: Props) {
  useEffect(() => {
    if (!open) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [open, onClose]);

  if (!open) return null;
  const isRoom = current?.type === 'room';
  const context = {
    mode: 'move' as const,
    source,
    currentType: current?.type,
    occupancyStatus: current?.occupancy?.status,
    moving,
  };
  const sofas = positions
    .filter((position) => position.type === 'sofa')
    .sort((left, right) => left.sort_order - right.sort_order);
  const leftSofas = sofas.filter((_, index) => index % 2 === 0);
  const rightSofas = sofas.filter((_, index) => index % 2 === 1);
  const availableTarget = sofas.find((position) => !position.is_current && position.state === 'available');
  const lockProbe = availableTarget || (current ? {
    ...current,
    is_current: false,
    state: 'available' as const,
    customer_selectable: true,
    operational_status: 'active',
  } : null);
  const moveDecision = lockProbe ? getPositionSelectionDecision(lockProbe, context) : null;

  const renderSeat = (position: ServicePosition) => {
    const decision = getPositionSelectionDecision(position, context);
    return (
      <button
        key={position.id}
        type="button"
        className={`plan-seat state-${position.is_current ? 'current' : position.state} ${decision.selectable ? '' : 'is-disabled'}`}
        aria-disabled={!decision.selectable}
        onClick={() => decision.selectable ? onSelect(position) : onBlocked(decision.reason)}
        aria-label={`${position.customer_label}，${decision.label}`}
      >
        <Sofa size={22} />
        <strong>{position.customer_label}</strong>
        <small>{decision.label}</small>
      </button>
    );
  };

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="seat-dialog" role="dialog" aria-modal="true" aria-labelledby="seat-map-title">
        <header className="dialog-header">
          <div>
            <span className="eyebrow">服务位核对</span>
            <h2 id="seat-map-title">{isRoom ? '房间已绑定' : '确认您所在的沙发'}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭服务位平面图"><X size={20} /></button>
        </header>

        {isRoom ? (
          <div className="room-locked">
            <span className="room-locked-icon">{isRoom ? <DoorClosed size={32} /> : <Sofa size={32} />}</span>
            <strong>{isRoom ? '当前房间' : current?.customer_label || '服务位置'}</strong>
            <p>此二维码已与房间绑定，无需选择；如位置不对请联系工作人员调整。</p>
          </div>
        ) : (
          <>
            {moveDecision && !moveDecision.selectable && (
              <div className="seat-map-notice"><strong>当前不可自行换位</strong><span>{moveDecision.reason}</span></div>
            )}
            <div className="seat-map-legend" aria-label="服务位状态图例">
              <span><i className="legend-dot current" />当前位置</span>
              <span><i className="legend-dot available" />可用</span>
              <span><i className="legend-dot busy" />有人</span>
            </div>
            <div className="store-plan" aria-label="门店服务位平面图">
              <div className="plan-entry-lane" aria-label="门口">
                <div className="plan-entry"><LocateFixed size={14} /><span>门口</span></div>
              </div>
              <div className="plan-seat-column" aria-label="左侧沙发区">{leftSofas.map(renderSeat)}</div>
              <div className="plan-walkway" aria-label="展示柜"><span>展示柜</span></div>
              <div className="plan-seat-column" aria-label="右侧沙发区">{rightSofas.map(renderSeat)}</div>
            </div>
            <p className="dialog-footnote">点任意沙发都会给出当前状态；空闲且允许自助换位时可直接切换。</p>
          </>
        )}
      </section>
    </div>
  );
}
