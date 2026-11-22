import { useEffect, useState } from 'react';
import { getRoomDoorEntry, type RoomDoorEntry } from '../api';
import './RoomDoorPage.css';

export default function RoomDoorPage({ code }: { code: string }) {
  const [entry, setEntry] = useState<RoomDoorEntry>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(''); setEntry(undefined);
    getRoomDoorEntry(code, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      setEntry(result);
      if (result.beds.length === 1 && result.beds[0].url) window.location.replace(result.beds[0].url);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '房间暂时无法打开');
    });
    return () => controller.abort();
  }, [code, attempt]);

  return <main className="room-door">
    {entry && <p className="room-door-store">{entry.store_name}</p>}
    <h1>{entry?.room_name || '房间点单'}</h1>
    {error ? <><p role="alert">{error}</p><button onClick={() => setAttempt(n => n + 1)}>重新加载</button></>
      : !entry ? <p role="status">正在读取房间信息…</p>
      : <>{entry.beds.length > 1 && <h2>请选择你所在的床位</h2>}
        {entry.beds.length === 1 && entry.beds[0].url && <p role="status">正在进入该床位的菜单…</p>}
        {!entry.beds.some(bed => bed.url) && <p>本房间暂时无法扫码点单，请联系前台。</p>}
        <ul>{entry.beds.map(bed => <li key={bed.code}>{bed.url
          ? <a href={bed.url}>{bed.name}<span aria-hidden="true">→</span></a>
          : <span className="room-door-disabled">{bed.name} · 暂不可用</span>}</li>)}</ul>
      </>}
  </main>;
}
