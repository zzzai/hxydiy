import type { ReactNode } from 'react';
import './service-portions.css';

export type ServicePortionRow = {
  key: string; name: string; status: 'requested' | 'assigned' | 'unassigned' | 'in_service' | 'completed';
  dispatched?: boolean;
  requested_label: string | null; label: string | null; technician_id: number | null; version: number;
  items: Array<{ name: string; preferences: string[] }>;
};

export default function ServicePortionRows({ portions, actions }: {
  portions: ServicePortionRow[];
  actions?: (portion: ServicePortionRow) => ReactNode;
}) {
  return <ol className="staff-service-portions">{portions.map((portion, index) => <li key={portion.key}>
    <strong>第 {index + 1} 份 · {portion.name}</strong>
    {portion.items.map((item, i) => {
      const text = [item.name !== portion.name ? item.name : '', ...item.preferences].filter(Boolean).join(' · ');
      return text && <div key={i}>{text}</div>;
    })}
    <div aria-live="polite">{({ requested: `点名 ${portion.requested_label} · 待店长确认`, unassigned: '门店安排',
      assigned: `${portion.label} · 店长已确认`, in_service: `${portion.label} · 服务中`,
      completed: `${portion.label} · 已完成` })[portion.status]}</div>
    {actions?.(portion)}
  </li>)}</ol>;
}
