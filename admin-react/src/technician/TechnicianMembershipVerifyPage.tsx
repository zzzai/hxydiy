import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Select, Spin } from 'antd';
import { CameraOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { consumeMembershipCode, getMembershipVerificationSelections, scanMembershipCode } from '../api';
import { attachCameraPreview } from './cameraPreview';

type Candidate = { selection_session_id: string; position_label: string; status: string; item_count: number };

export default function TechnicianMembershipVerifyPage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<Candidate[]>([]);
  const [selectionId, setSelectionId] = useState('');
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<any>();
  const [pending, setPending] = useState<any>();
  const [error, setError] = useState('');
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream>();
  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);
  const loadCandidates = async () => {
    const { data } = await getMembershipVerificationSelections();
    setItems(data.items);
    if (data.items.length === 1) setSelectionId(data.items[0].selection_session_id);
    else setSelectionId('');
    return data.items as Candidate[];
  };
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
            try {
              const response = await scanMembershipCode(codes[0].rawValue);
              const candidates = await loadCandidates();
              if (!candidates.length) throw new Error('当前没有可绑定的顾客服务单');
              setPending({ ...response.data, codeToken: codes[0].rawValue });
            } catch (reason: any) { setError(reason?.response?.data?.detail?.message || reason?.message || '会员码预检失败'); }
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
  return <section className="technician-member-verify"><h2>会员核验</h2><p>直接扫描顾客手机上的动态会员码，扫码后再匹配本次服务单。</p><Card><Button type="primary" size="large" icon={<CameraOutlined />} onClick={scanning ? stop : start}>{scanning ? '停止扫码' : '打开摄像头扫码'}</Button></Card>{scanning && <div className="technician-member-camera"><video ref={setVideo} playsInline muted autoPlay /><Spin tip="正在识别会员码" /></div>}{error && <Alert type="error" showIcon message={error} />}{pending && <Card className="technician-member-result"><h3>请核对会员信息</h3><p>{pending.member.name_masked}　{pending.member.phone_masked}</p>{items.length > 1 && <><label>选择本次服务单</label><Select value={selectionId || undefined} placeholder="请选择顾客本次服务单" onChange={setSelectionId} options={items.map((item) => ({ value: item.selection_session_id, label: `${item.position_label} · ${item.item_count}项` }))} /></>}<Button type="primary" size="large" disabled={!selectionId} onClick={() => void confirm()}>确认绑定本次服务单</Button></Card>}{result && <Card className="technician-member-result"><CheckCircleOutlined /><h3>会员核验成功</h3><p>{result.member.name_masked}　{result.member.phone_masked}</p><p>会员有效期：{result.member.member_expire_at ? String(result.member.member_expire_at).slice(0, 10) : '以门店记录为准'}</p><strong>已按服务端会员规则重新计算本次服务单</strong></Card>}<Alert type="info" showIcon message="核验只绑定本次服务单，不确认或结束服务，也不修改物理服务位状态。" /></section>;
}
