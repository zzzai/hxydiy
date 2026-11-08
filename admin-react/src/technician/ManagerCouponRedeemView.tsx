import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Input, Spin, Tag } from 'antd';
import { CameraOutlined, ScanOutlined } from '@ant-design/icons';
import { redeemManagerCoupon, validateManagerCoupon } from '../api';

type CouponPreview = {
  coupon_id: number;
  customer_name: string;
  phone_masked: string;
  name: string;
  percent_off?: number | null;
  amount_cents?: number | null;
  min_spend_cents?: number | null;
  expire_at?: string | null;
  status: string;
};

export default function ManagerCouponRedeemView({ initialToken = '' }: { initialToken?: string }) {
  const [token, setToken] = useState('');
  const [preview, setPreview] = useState<CouponPreview | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [cameraBusy, setCameraBusy] = useState(false);
  const [cameraError, setCameraError] = useState('');
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const scanRef = useRef(false);

  const stopCamera = () => {
    scanRef.current = false;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraBusy(false);
  };

  useEffect(() => () => stopCamera(), []);

  useEffect(() => { if (initialToken) void validate(initialToken); }, [initialToken]);

  const validate = async (raw = token) => {
    const value = raw.trim();
    if (!value || busy) return;
    setBusy(true); setError(''); setSuccess(''); setPreview(null);
    try {
      const response = await validateManagerCoupon(value);
      setToken(value);
      setPreview(response.data as CouponPreview);
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
      setError(detail?.message || '核销码无效或已过期');
    } finally {
      setBusy(false);
    }
  };

  const redeem = async () => {
    if (!preview || busy) return;
    setBusy(true); setError(''); setSuccess('');
    try {
      const response = await redeemManagerCoupon(token, crypto.randomUUID());
      setSuccess(`${response.data.customer_name} 的「${response.data.name}」已核销，券已失效。`);
      setPreview(null);
      setToken('');
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
      setError(detail?.message || '核销失败，请重试');
      setPreview(null);
    } finally {
      setBusy(false);
    }
  };

  const startCamera = async () => {
    if (cameraBusy) return;
    setCameraError('');
    const detectorClass = (window as unknown as { BarcodeDetector?: new (options: { formats: string[] }) => { detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue: string }>> } }).BarcodeDetector;
    if (!detectorClass || !navigator.mediaDevices?.getUserMedia) {
      setCameraError('当前浏览器不支持相机扫码，请让顾客把核销码发给你，粘贴到下方。');
      return;
    }
    setCameraBusy(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      const detector = new detectorClass({ formats: ['qr_code'] });
      scanRef.current = true;
      const scan = async () => {
        if (!scanRef.current || !videoRef.current) return;
        try {
          const codes = await detector.detect(videoRef.current);
          const value = codes[0]?.rawValue?.trim();
          if (value) {
            stopCamera();
            await validate(value);
            return;
          }
        } catch { /* keep scanning */ }
        if (scanRef.current) requestAnimationFrame(() => void scan());
      };
      void scan();
    } catch {
      stopCamera();
      setCameraError('无法打开相机，请检查浏览器权限，或粘贴核销码。');
    }
  };

  return <section className="manager-coupon-redeem" aria-label="优惠券核销">
    <div className="manager-tasks-heading">
      <div><h2>优惠券核销</h2><p>扫描顾客券码，确认后券立即失效；只核销，不改订单金额。</p></div>
      <Tag color="green">店长</Tag>
    </div>
    <div className="manager-coupon-scan">
      <Button icon={<CameraOutlined />} onClick={() => void startCamera()} loading={cameraBusy}>打开相机扫码</Button>
      <video ref={videoRef} className="manager-coupon-video" muted playsInline />
      {cameraError && <Alert type="info" showIcon message={cameraError} />}
      <Input.TextArea value={token} onChange={(event) => { setToken(event.target.value); setPreview(null); setError(''); }} autoSize={{ minRows: 2, maxRows: 4 }} placeholder="或粘贴顾客券码" />
      <Button type="primary" icon={<ScanOutlined />} disabled={!token.trim() || busy} onClick={() => void validate()}>{busy ? '校验中…' : '校验券码'}</Button>
    </div>
    {error && <Alert type="error" showIcon message={error} />}
    {success && <Alert type="success" showIcon message={success} />}
    {busy && !preview && <div className="manager-empty"><Spin size="small" /><span>正在校验</span></div>}
    {preview && <div className="manager-coupon-preview">
      <div><strong>{preview.name}</strong><Tag color="green">可核销</Tag></div>
      <dl>
        <div><dt>顾客</dt><dd>{preview.customer_name} · {preview.phone_masked}</dd></div>
        <div><dt>优惠</dt><dd>{preview.percent_off ? `${preview.percent_off / 10}折` : `¥${((preview.amount_cents || 0) / 100).toFixed(0)}`}</dd></div>
        <div><dt>有效期</dt><dd>{preview.expire_at ? new Date(preview.expire_at).toLocaleDateString('zh-CN') : '—'}</dd></div>
      </dl>
      <p className="manager-detail-note">确认后券立即变为“已使用”。本次不抵扣当前订单金额。</p>
      <Button type="primary" block loading={busy} onClick={() => void redeem()}>确认核销</Button>
    </div>}
  </section>;
}
