import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Select, Spin } from 'antd';
import { CameraOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { consumeMembershipCode, getMembershipVerificationSelections, scanMembershipCode } from '../api';

type Candidate = { selection_session_id: string; position_label: string; status: string; item_count: number };

export default function TechnicianMembershipVerifyPage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<Candidate[]>([]);
  const [selectionId, setSelectionId] = useState('');
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<any>();
  const [pending, setPending] = useState<any>();
  const [error, setError] = useState('');
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream>();
  useEffect(() => { void getMembershipVerificationSelections().then(({ data }) => { setItems(data.items); if (data.items.length === 1) setSelectionId(data.items[0].selection_session_id); }).catch(() => setError('加载本店待核验选单失败')); return () => streamRef.current?.getTracks().forEach((track) => track.stop()); }, []);
  const stop = () => { streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = undefined; setScanning(false); };
  const start = async () => {
    if (!selectionId) { message.warning('请先选择服务位置'); return; }
    setError(''); setResult(undefined);
    try {
      const Detector = (globalThis as any).BarcodeDetector;
      if (!Detector) throw new Error('当前浏览器不支持扫码，请升级 Chrome');
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      streamRef.current = stream; setScanning(true);
      if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play(); }
      const detector = new Detector({ formats: ['qr_code'] });
      const scan = async () => {
        if (!streamRef.current || !videoRef.current) return;
        const codes = await detector.detect(videoRef.current).catch(() => []);
        if (codes[0]?.rawValue) { stop(); try { const response = await scanMembershipCode(codes[0].rawValue); setPending({ ...response.data, codeToken: codes[0].rawValue }); } catch (reason: any) { setError(reason?.response?.data?.detail?.message || '会员码预检失败'); } return; }
        window.setTimeout(scan, 250);
      };
      void scan();
    } catch (reason) { stop(); setError(reason instanceof Error ? reason.message : '无法启动摄像头'); }
  };
  const confirm = async () => { if (!pending || !selectionId) return; try { const response = await consumeMembershipCode(pending.codeToken, selectionId); setResult(response.data); setPending(undefined); message.success('会员核验成功'); } catch (reason: any) { setError(reason?.response?.data?.detail?.message || '会员绑定失败'); } };
  return <section className="technician-member-verify"><h2>会员核验</h2><p>先选择顾客所在服务位，再扫描顾客手机上的30秒动态会员码。</p><Card><label>本店待核验选单</label><Select value={selectionId || undefined} placeholder="选择服务位置" onChange={setSelectionId} options={items.map((item) => ({ value: item.selection_session_id, label: `${item.position_label} · ${item.item_count}项` }))} /><Button type="primary" size="large" icon={<CameraOutlined />} onClick={scanning ? stop : start}>{scanning ? '停止扫码' : '打开摄像头扫码'}</Button></Card>{scanning && <div className="technician-member-camera"><video ref={videoRef} playsInline muted /><Spin tip="正在识别会员码" /></div>}{error && <Alert type="error" showIcon message={error} />}{pending && <Card className="technician-member-result"><h3>请核对会员信息</h3><p>{pending.member.name_masked}　{pending.member.phone_masked}</p><Button type="primary" size="large" onClick={() => void confirm()}>确认绑定本次选单</Button></Card>}{result && <Card className="technician-member-result"><CheckCircleOutlined /><h3>会员核验成功</h3><p>{result.member.name_masked}　{result.member.phone_masked}</p><p>会员有效期：{result.member.member_expire_at ? String(result.member.member_expire_at).slice(0, 10) : '以门店记录为准'}</p><strong>已按服务端会员规则重新计算本次选单</strong></Card>}<Alert type="info" showIcon message="核验只绑定本次选单，不确认或结束服务，也不修改物理服务位状态。" /></section>;
}
