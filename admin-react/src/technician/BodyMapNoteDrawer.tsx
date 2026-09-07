import { ArrowLeftOutlined, CheckCircleFilled, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { App, Button, Drawer, Radio, Tag, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import bodyMapImage from '../assets/technician-body-map.png';
import { getTechnicianServiceReferenceTaxonomy } from '../api';
import { bodyMapPointKey, toggleBodyMapPoint, type BodyMapPoint } from './bodyMap';
import type { V5BodyContext, V5BodyCurrentState, V5BodyRegion, V5BodyServiceNote, V5BodySessionHandling, V5BodySide } from './serviceReference';

type DraftNote = BodyMapPoint & Partial<Omit<V5BodyServiceNote, 'region' | 'side'>>;
type PointLayout = BodyMapPoint & { label: string; x: number; y: number };

const REGIONS: Record<V5BodyRegion, string> = {
  head: '头部', neck: '颈部', shoulder: '肩部', chest: '胸部', abdomen: '腹部', upper_back: '上背', mid_back: '中背', lower_back: '下背', side_waist: '侧腰', upper_arm: '上臂', elbow: '肘部', wrist: '腕部', hand: '手部', hip: '髋部', buttock: '臀部', thigh: '大腿', knee: '膝部', calf: '小腿', ankle: '踝部', foot: '足部',
};

const CONTEXTS: Array<{ value: V5BodyContext; label: string }> = [
  { value: 'previous_injury_mentioned', label: '顾客提及曾受伤' }, { value: 'post_procedure_recovery_mentioned', label: '顾客提及术后恢复中' }, { value: 'recent_discomfort_mentioned', label: '顾客提及近期不适' }, { value: 'long_term_discomfort_mentioned', label: '顾客提及长期不适' }, { value: 'skin_sensitivity_mentioned', label: '顾客提及皮肤敏感' }, { value: 'reconfirm_requested', label: '情况需到店确认' },
];
const STATES: Array<{ value: V5BodyCurrentState; label: string }> = [
  { value: 'currently_uncomfortable', label: '当前仍有不适' }, { value: 'occasional_discomfort', label: '偶尔不适' }, { value: 'no_current_discomfort', label: '目前无明显不适' }, { value: 'needs_reconfirmation', label: '当前情况需再确认' },
];
const HANDLINGS: Array<{ value: V5BodySessionHandling; label: string }> = [
  { value: 'avoid', label: '本次避开' }, { value: 'lighter', label: '本次减轻力度' }, { value: 'normal_after_confirmation', label: '确认后正常进行' }, { value: 'observe_and_reconfirm', label: '本次观察，下次再确认' },
];

// x/y coordinates are percentage positions over the generated front/back silhouette image.
const POINTS: PointLayout[] = [
  { region: 'head', side: 'center', label: '头部', x: 25, y: 13 }, { region: 'neck', side: 'center', label: '颈部', x: 25, y: 22 },
  { region: 'shoulder', side: 'right', label: '右肩', x: 16, y: 27 }, { region: 'shoulder', side: 'left', label: '左肩', x: 34, y: 27 },
  { region: 'chest', side: 'center', label: '胸部', x: 25, y: 33 }, { region: 'abdomen', side: 'center', label: '腹部', x: 25, y: 43 },
  { region: 'upper_arm', side: 'right', label: '右上臂', x: 12, y: 36 }, { region: 'upper_arm', side: 'left', label: '左上臂', x: 38, y: 36 },
  { region: 'elbow', side: 'right', label: '右肘', x: 11, y: 48 }, { region: 'elbow', side: 'left', label: '左肘', x: 39, y: 48 },
  { region: 'wrist', side: 'right', label: '右腕', x: 10, y: 59 }, { region: 'wrist', side: 'left', label: '左腕', x: 40, y: 59 },
  { region: 'hand', side: 'right', label: '右手', x: 8, y: 64 }, { region: 'hand', side: 'left', label: '左手', x: 42, y: 64 },
  { region: 'side_waist', side: 'right', label: '右侧腰', x: 20, y: 47 }, { region: 'side_waist', side: 'left', label: '左侧腰', x: 30, y: 47 },
  { region: 'hip', side: 'right', label: '右髋', x: 21, y: 54 }, { region: 'hip', side: 'left', label: '左髋', x: 29, y: 54 },
  { region: 'thigh', side: 'right', label: '右大腿', x: 21, y: 64 }, { region: 'thigh', side: 'left', label: '左大腿', x: 29, y: 64 },
  { region: 'knee', side: 'right', label: '右膝', x: 21, y: 76 }, { region: 'knee', side: 'left', label: '左膝', x: 29, y: 76 },
  { region: 'calf', side: 'right', label: '右小腿', x: 21, y: 84 }, { region: 'calf', side: 'left', label: '左小腿', x: 29, y: 84 },
  { region: 'ankle', side: 'right', label: '右踝', x: 21, y: 91 }, { region: 'ankle', side: 'left', label: '左踝', x: 29, y: 91 },
  { region: 'foot', side: 'right', label: '右足', x: 20, y: 96 }, { region: 'foot', side: 'left', label: '左足', x: 30, y: 96 },
  { region: 'upper_back', side: 'center', label: '上背', x: 75, y: 33 }, { region: 'mid_back', side: 'center', label: '中背', x: 75, y: 42 }, { region: 'lower_back', side: 'center', label: '下背', x: 75, y: 49 },
  // 背面图中画面右侧才是顾客本人右侧；所有侧别均按顾客身体左右保存。
  { region: 'shoulder', side: 'left', label: '左肩', x: 66, y: 27 }, { region: 'shoulder', side: 'right', label: '右肩', x: 84, y: 27 },
  { region: 'upper_arm', side: 'left', label: '左上臂', x: 62, y: 36 }, { region: 'upper_arm', side: 'right', label: '右上臂', x: 88, y: 36 },
  { region: 'elbow', side: 'left', label: '左肘', x: 61, y: 48 }, { region: 'elbow', side: 'right', label: '右肘', x: 89, y: 48 },
  { region: 'wrist', side: 'left', label: '左腕', x: 60, y: 59 }, { region: 'wrist', side: 'right', label: '右腕', x: 90, y: 59 },
  { region: 'hand', side: 'left', label: '左手', x: 58, y: 64 }, { region: 'hand', side: 'right', label: '右手', x: 92, y: 64 },
  { region: 'side_waist', side: 'left', label: '左侧腰', x: 70, y: 47 }, { region: 'side_waist', side: 'right', label: '右侧腰', x: 80, y: 47 },
  { region: 'hip', side: 'left', label: '左髋', x: 71, y: 53 }, { region: 'hip', side: 'right', label: '右髋', x: 79, y: 53 },
  { region: 'buttock', side: 'left', label: '左臀', x: 71, y: 56 }, { region: 'buttock', side: 'right', label: '右臀', x: 79, y: 56 },
  { region: 'thigh', side: 'left', label: '左大腿', x: 71, y: 64 }, { region: 'thigh', side: 'right', label: '右大腿', x: 79, y: 64 },
  { region: 'knee', side: 'left', label: '左膝', x: 71, y: 76 }, { region: 'knee', side: 'right', label: '右膝', x: 79, y: 76 },
  { region: 'calf', side: 'left', label: '左小腿', x: 71, y: 84 }, { region: 'calf', side: 'right', label: '右小腿', x: 79, y: 84 },
  { region: 'ankle', side: 'left', label: '左踝', x: 71, y: 91 }, { region: 'ankle', side: 'right', label: '右踝', x: 79, y: 91 },
  { region: 'foot', side: 'left', label: '左足', x: 70, y: 96 }, { region: 'foot', side: 'right', label: '右足', x: 80, y: 96 },
];

const description = (note: DraftNote) => {
  const context = CONTEXTS.find((item) => item.value === note.context)?.label;
  return context ? `${REGIONS[note.region]}${note.side === 'left' ? '（左）' : note.side === 'right' ? '（右）' : ''} · ${context}` : `${REGIONS[note.region]}${note.side === 'left' ? '（左）' : note.side === 'right' ? '（右）' : ''} · 待补充`;
};
const complete = (note: DraftNote): note is V5BodyServiceNote => Boolean(note.context && note.currentState && note.sessionHandling && note.reconfirmNextVisit);

export default function BodyMapNoteDrawer({ open, value, onChange, onClose, context }: { open: boolean; value: V5BodyServiceNote[]; onChange: (value: V5BodyServiceNote[]) => void; onClose: () => void; context: string }) {
  const { message } = App.useApp();
  const [step, setStep] = useState(1);
  const [notes, setNotes] = useState<DraftNote[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [taxonomy, setTaxonomy] = useState<any>(null);

  useEffect(() => {
    if (!open) return;
    setStep(1);
    setNotes(value.map((note) => ({ ...note })));
    setActiveKey(null);
  }, [open, value]);

  // 服务端 taxonomy 是唯一权威；本地文案仅用于网络短暂失败时不中断当次服务记录。
  useEffect(() => {
    if (!open) return;
    getTechnicianServiceReferenceTaxonomy().then((response) => {
      const body = response.data;
      if (body?.schema_version === 5 && body?.taxonomy_version === 'service_reference_v4') setTaxonomy(body.groups?.body_service_notes || null);
    }).catch(() => undefined);
  }, [open]);

  const regionLabels = taxonomy?.regions || REGIONS;
  const contexts = Object.entries(taxonomy?.contexts || Object.fromEntries(CONTEXTS.map((item) => [item.value, item.label]))).map(([value, label]) => ({ value: value as V5BodyContext, label: String(label) }));
  const states = Object.entries(taxonomy?.current_states || Object.fromEntries(STATES.map((item) => [item.value, item.label]))).map(([value, label]) => ({ value: value as V5BodyCurrentState, label: String(label) }));
  const handlings = Object.entries(taxonomy?.session_handlings || Object.fromEntries(HANDLINGS.map((item) => [item.value, item.label]))).map(([value, label]) => ({ value: value as V5BodySessionHandling, label: String(label) }));

  const active = notes.find((note) => bodyMapPointKey(note) === activeKey) || null;
  const selectedPoints = useMemo(() => notes.map(({ region, side }) => ({ region, side })), [notes]);
  const patchActive = (patch: Partial<DraftNote>) => activeKey && setNotes((current) => current.map((note) => bodyMapPointKey(note) === activeKey ? { ...note, ...patch } : note));
  const choosePoint = (point: BodyMapPoint) => {
    const key = bodyMapPointKey(point);
    if (!selectedPoints.some((item) => bodyMapPointKey(item) === key) && selectedPoints.length >= 3) { message.warning('最多记录 3 个部位'); return; }
    const nextPoints = toggleBodyMapPoint(selectedPoints, point);
    setNotes((current) => nextPoints.map((next) => current.find((item) => bodyMapPointKey(item) === bodyMapPointKey(next)) || { ...next, reconfirmNextVisit: true }));
  };
  const startDetails = () => {
    if (!notes.length) { message.warning('请先选择身体部位'); return; }
    const first = notes.find((note) => !complete(note)) || notes[0];
    setActiveKey(bodyMapPointKey(first));
    setStep(2);
  };
  const advance = () => {
    if (!active) return;
    if (step === 2 && !active.context) { message.warning('请选择顾客自述情况'); return; }
    if (step === 3 && !active.currentState) { message.warning('请选择当前状态'); return; }
    if (step < 4) { setStep((current) => current + 1); return; }
    if (!active.sessionHandling) { message.warning('请选择本次处理'); return; }
    const next = notes.find((note) => bodyMapPointKey(note) !== activeKey && !complete(note));
    if (next) { setActiveKey(bodyMapPointKey(next)); setStep(2); return; }
    onChange(notes.filter(complete));
    onClose();
  };
  const remove = (key: string) => setNotes((current) => current.filter((note) => bodyMapPointKey(note) !== key));

  const footer = step === 1 ? <Button type="primary" block size="large" onClick={startDetails}>下一步：填写顾客自述</Button> : <div className="technician-body-map-footer"><Button size="large" onClick={() => setStep((current) => current - 1)}>上一步</Button><Button type="primary" size="large" onClick={advance}>{step === 4 ? '保存此部位' : '下一步'}</Button></div>;

  return <Drawer title={step === 1 ? '记录身体相关情况' : `记录身体相关情况 · 第 ${step} 步`} placement="bottom" height="100vh" open={open} onClose={onClose} className="technician-body-map-drawer" footer={footer} closeIcon={step === 1 ? undefined : <ArrowLeftOutlined onClick={() => setStep((current) => current - 1)} />}>
    <div className="technician-profile-context"><Typography.Text strong>{context}</Typography.Text><Typography.Text type="secondary">只记录顾客自述，不作诊断</Typography.Text></div>
    <div className="technician-body-map-steps" aria-label={`当前第 ${step} 步，共 4 步`}><span className={step >= 1 ? 'active' : ''}>1<br />选部位</span><span className={step >= 2 ? 'active' : ''}>2<br />选情况</span><span className={step >= 3 ? 'active' : ''}>3<br />当前状态</span><span className={step >= 4 ? 'active' : ''}>4<br />本次处理</span></div>
    {step === 1 && <>
      <Typography.Title level={4}>点击选择身体部位（可多选）</Typography.Title>
      <div className="technician-body-map-canvas"><img src={bodyMapImage} alt="正面与背面人体轮廓" />{POINTS.map((point, index) => {
        const selected = selectedPoints.some((item) => bodyMapPointKey(item) === bodyMapPointKey(point));
        return <button className={`technician-body-map-point ${selected ? 'selected' : ''}`} key={`${bodyMapPointKey(point)}-${index}`} style={{ left: `${point.x}%`, top: `${point.y}%` }} aria-label={`选择${point.label}`} onClick={() => choosePoint(point)}>{selected ? <CheckCircleFilled /> : null}</button>;
      })}</div>
      <div className="technician-body-map-selected"><Typography.Text strong>已选择 {notes.length} 个部位</Typography.Text>{notes.length > 0 && <Button type="link" onClick={() => setNotes([])}>清空</Button>}</div>
      {notes.map((note, index) => <div className="technician-body-map-note" key={bodyMapPointKey(note)}><span>{index + 1}</span><Typography.Text>{description(note)}</Typography.Text><Button type="text" aria-label={`编辑${description(note)}`} icon={<EditOutlined />} onClick={() => { setActiveKey(bodyMapPointKey(note)); setStep(2); }} /><Button danger type="text" aria-label={`删除${description(note)}`} icon={<DeleteOutlined />} onClick={() => remove(bodyMapPointKey(note))} /></div>)}
    </>}
    {step > 1 && active && <section className="technician-body-map-choice"><Typography.Title level={4}>{regionLabels[active.region] || REGIONS[active.region]}{active.side === 'left' ? '（左）' : active.side === 'right' ? '（右）' : ''}</Typography.Title>{step === 2 && <><Typography.Paragraph>顾客提及的情况</Typography.Paragraph><Radio.Group value={active.context} onChange={(event) => patchActive({ context: event.target.value })} options={contexts} optionType="button" buttonStyle="solid" /></>}{step === 3 && <><Typography.Paragraph>当前状态</Typography.Paragraph><Radio.Group value={active.currentState} onChange={(event) => patchActive({ currentState: event.target.value })} options={states} optionType="button" buttonStyle="solid" /></>}{step === 4 && <><Typography.Paragraph>本次处理</Typography.Paragraph><Radio.Group value={active.sessionHandling} onChange={(event) => patchActive({ sessionHandling: event.target.value })} options={handlings} optionType="button" buttonStyle="solid" /><Typography.Paragraph type="secondary">下次服务前仍需当面确认。</Typography.Paragraph></>}</section>}
  </Drawer>;
}
