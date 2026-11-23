import { useEffect, useState } from 'react';
import { selectableTechnicians, type SelectableTechnician } from '../api';

type Props = {
  storeId: number;
  projectId: number;
  value?: SelectableTechnician;
  onChange: (value?: SelectableTechnician) => void;
};

export default function PortionTechnicianPicker({ storeId, projectId, value, onChange }: Props) {
  const [items, setItems] = useState<SelectableTechnician[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setStatus('loading');
    setItems([]);
    selectableTechnicians(storeId, projectId, controller.signal).then(list => {
      if (controller.signal.aborted) return;
      setItems(list);
      setStatus('ready');
      if (value && !list.some(item => item.id === value.id)) onChange(undefined);
    }).catch(() => { if (!controller.signal.aborted) setStatus('error'); });
    return () => controller.abort();
  }, [storeId, projectId, attempt]);

  return <section className="mini-config-card portion-technician" aria-label="本份服务技师">
    <div className="mini-config-title"><strong>服务技师</strong>
      {status === 'ready' && items.length > 0
        ? <select aria-label="本份服务技师" value={value?.id ?? ''} onChange={event => onChange(items.find(item => item.id === Number(event.target.value)))}>
            <option value="">门店安排</option>
            {items.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        : <span>{value?.label || '门店安排'}</span>}
    </div>
    {value && <p className="portion-hint" role="status">点名后由店长确认</p>}
    {status === 'error' && <div className="portion-hint" role="status">暂时无法加载技师名单 <button type="button" onClick={() => setAttempt(current => current + 1)}>重试</button>{value && <button type="button" onClick={() => onChange(undefined)}>改为门店安排</button>}</div>}
  </section>;
}
