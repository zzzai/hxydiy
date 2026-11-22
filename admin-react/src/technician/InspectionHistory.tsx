import { useCallback, useEffect, useRef, useState } from 'react';
import { getManagerDaily, type InspectionArea } from '../api';
import ManagerAreaPhotos from './ManagerAreaPhotos';
import { useTechnicianSession } from './useTechnicianSession';

type Day = { business_date: string; areas: InspectionArea[]; inspection_ai_enabled: boolean };
function previousDay(today: string, days: number) {
  const date = new Date(today + 'T12:00:00Z');
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

function PastPhotos({ today }: { today: string }) {
  const last = previousDay(today, 1);
  const first = previousDay(today, 89);
  const [date, setDate] = useState(last);
  const [day, setDay] = useState<Day | null>(null);
  const [failed, setFailed] = useState(false);
  const current = useTechnicianSession();
  const sequence = useRef(0);
  const refresh = useCallback(async () => {
    const version = ++sequence.current;
    if (!date || date < first || date > last) return;
    setFailed(false);
    try {
      const { data } = await getManagerDaily(date);
      if (current() && version === sequence.current && data.business_date === date) setDay(data);
    } catch {
      if (current() && version === sequence.current) setFailed(true);
    }
  }, [date, first, last, current]);
  useEffect(() => {
    void refresh();
    return () => { sequence.current++; };
  }, [refresh]);
  const shown = day?.business_date === date ? day : null;
  const areas = shown?.areas.filter(area => area.photos?.length || area.photo);
  return <div className="inspection-history">
    <label>巡检日期 <input type="date" value={date} min={first} max={last} onChange={event => setDate(event.target.value)} /></label>
    <button type="button" className="manager-p0-text-link" onClick={() => void refresh()}>刷新记录</button>
    {failed ? <p role="status">暂时无法读取这天的记录，请刷新。</p>
      : !date || date < first || date > last ? <p role="status">请选择近 90 天内已结束的营业日。</p>
      : !shown ? <p role="status">正在读取照片…</p>
      : areas?.length ? <ManagerAreaPhotos historical areas={areas} reviewEnabled={shown.inspection_ai_enabled}
        businessDate={date} submitted disabled={false} onRefresh={refresh} />
      : <p role="status">这天没有巡检照片。</p>}
  </div>;
}

export default function InspectionHistory({ today }: { today: string }) {
  const [open, setOpen] = useState(false);
  return <section className="manager-p0-card">
    <button type="button" className="manager-p0-text-link" aria-expanded={open} onClick={() => setOpen(!open)}>
      {open ? '收起过往巡检' : '查看过往巡检照片'}
    </button>
    {open && <PastPhotos today={today} />}
  </section>;
}
