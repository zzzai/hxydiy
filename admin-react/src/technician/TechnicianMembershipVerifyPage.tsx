import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Select, Spin } from 'antd';
import { CameraOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { consumeMembershipCode, getMembershipVerificationSelections, scanMembershipCode } from '../api';
import { attachCameraPreview } from './cameraPreview';
import { membershipVerificationView } from './membershipVerification';

type Candidate = { selection_session_id: string; position_label: string; status: string; item_count: number };

export default function TechnicianMembershipVerifyPage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<Candidate[]>([]);
  const [blockedPositions, setBlockedPositions] = useState<{ position_label: string; active_count: number }[]>([]);
  const [selectionId, setSelectionId] = useState('');
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<any>();
  const [pending, setPending] = useState<any>();
  const [error, setError] = useState('');
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream>();
  useEffect(() => { void getMembershipVerificationSelections().then(({ data }) => { setItems(data.items); setBlockedPositions(data.blocked_positions || []); if (data.items.length === 1) setSelectionId(data.items[0].selection_session_id); }).catch(() => setError('加载本店可绑定选单失败，扫码后请刷新重试')); return () => streamRef.current?.getTracks().forEach((track) => track.stop()); }, []);
  const stop = () => { streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = undefined; setScanning(false); };
  const start = async () => {
    setError(''); setResult(undefined);
    try {
      const Detector = (globalThis as any).BarcodeDetector;
      if (!Detector) throw new Error('当前浏览器不支持扫码，请升级 Chrome');
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      streamRef.current = stream; setScanning(true);
    } catch (reason) { stop(); setError(reason instanceof Error ? reason.message : '无法启动摄像头'); }
  };
  useEffect(() => {
    if (!scanning || !video || !streamRef.current) return;
    let active = true;
    const Detector = (globalThis as any).BarcodeDetector;
    const scan = async () => {
      try {
        await attachCameraPreview(video, streamRef.current!);
        const detector = new Detector({ formats: ['qr_code'] });
        while (active && streamRef.current) {
          const codes = await detector.detect(video).catch(() => []);
          if (codes[0]?.rawValue) {
            stop();
            try { const response = await scanMembershipCode(codes[0].rawValue); setPending({ ...response.data, codeToken: codes[0].rawValue }); } catch (reason: any) { setError(reason?.response?.data?.detail?.message || '会员码预检失败'); }
            return;
          }
          await new Promise((resolve) => window.setTimeout(resolve, 250));
        }
      } catch (reason) {
        stop();
        setError(reason instanceof Error ? reason.message : '无法启动摄像头');
      }
    };
    void scan();
    return () => { active = false; };
  }, [scanning, video]);
  const confirm = async () => { if (!pending || !selectionId) return; try { const response = await consumeMembershipCode(pending.codeToken, selectionId); setResult(response.data); setPending(undefined); message.success('会员核验成功'); } catch (reason: any) { setError(reason?.response?.data?.detail?.message || '会员绑定失败'); } };
  const view = membershipVerificationView(Boolean(pending), blockedPositions.length);
  return <section className="technician-member-verify"><h2>会员核验</h2><p>仅在顾客使用会员权益时扫码；普通顾客无需操作，照常开始服务。</p>{view.blockedMessage && <Alert type="warning" showIcon message={view.blockedMessage} />}{!pending && <Card><label>扫描顾客手机上的30秒动态会员码</label><Button type="primary" size="large" icon={<CameraOutlined />} onClick={scanning ? stop : start}>{scanning ? '停止扫码' : view.primaryAction}</Button></Card>}{scanning && <div className="technician-member-camera"><video ref={setVideo} playsInline muted autoPlay /><Spin tip="正在识别会员码" /></div>}{error && <Alert type="error" showIcon message={error} />}{pending && <Card className="technician-member-result"><h3>已识别会员</h3><p>{pending.member.name_masked}　{pending.member.phone_masked}</p><label>绑定到本次服务位</label><Select value={selectionId || undefined} placeholder="选择本次服务位" onChange={setSelectionId} options={items.map((item) => ({ value: item.selection_session_id, label: `${item.position_label} · ${item.item_count}项` }))} /><Button type="primary" size="large" disabled={!selectionId} onClick={() => void confirm()}>{view.primaryAction}</Button></Card>}{result && <Card className="technician-member-result"><CheckCircleOutlined /><h3>会员核验成功</h3><p>{result.member.name_masked}　{result.member.phone_masked}</p><p>会员有效期：{result.member.member_expire_at ? String(result.member.member_expire_at).slice(0, 10) : '以门店记录为准'}</p><strong>已按服务端会员规则重新计算本次选单</strong></Card>}<Alert type="info" showIcon message="核验只绑定本次选单，不确认或结束服务，也不修改物理服务位状态。" /></section>;
}
