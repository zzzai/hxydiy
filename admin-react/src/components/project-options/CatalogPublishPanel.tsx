import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Descriptions, List, Space, Tag, message } from 'antd';
import { getOptionGroups, previewCatalogPrice, publishCatalog, validateCatalogPublication } from '../../api';
import { catalogPublishState, formatCents, nextTuesdayIso, previewChoiceIds } from '../../catalogOptions';

const STORE_TIMEZONE = 'Asia/Shanghai';

export default function CatalogPublishPanel({ projectId, blocked = false }: { projectId: number; blocked?: boolean }) {
  const [validation, setValidation] = useState<any>({ valid: false, errors: [] });
  const [version, setVersion] = useState<any>(null);
  const [preview, setPreview] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [previewError, setPreviewError] = useState(false);
  const [publishError, setPublishError] = useState(false);
  const requestId = useRef(0);
  const load = async () => {
    const request = ++requestId.current;
    setChecking(true); setLoadError(false); setPreviewError(false); setPreview(null);
    try {
    const [check, groups] = await Promise.all([validateCatalogPublication(projectId), getOptionGroups(projectId)]);
    if (request !== requestId.current) return;
    setVersion(groups.data?.catalog_version || null);
    setValidation(check.data || { valid: false, errors: [] });
    const optionGroups = groups.data?.items || [];
    const choices = previewChoiceIds(optionGroups);
    const confirmedAt = new Date().toISOString();
    try {
      const [store, member, tuesday] = await Promise.all([
        previewCatalogPrice(projectId, {
          choice_ids: choices, is_member: false, confirmed_at: confirmedAt, store_timezone: STORE_TIMEZONE,
        }),
        previewCatalogPrice(projectId, {
          choice_ids: choices, is_member: true, confirmed_at: confirmedAt, store_timezone: STORE_TIMEZONE,
        }),
        previewCatalogPrice(projectId, {
          choice_ids: choices, is_member: true, confirmed_at: nextTuesdayIso(STORE_TIMEZONE), store_timezone: STORE_TIMEZONE,
        }),
      ]);
      if (request !== requestId.current) return;
      setPreview({
        store_total_cents: store.data?.total_cents,
        member_total_cents: member.data?.total_cents,
        tuesday_total_cents: tuesday.data?.total_cents,
      });
    } catch { if (request === requestId.current) setPreviewError(true); }
    } catch { if (request === requestId.current) setLoadError(true); }
    finally { if (request === requestId.current) setChecking(false); }
  };
  useEffect(() => { void load(); return () => { requestId.current++; }; }, [projectId]);
  const state = catalogPublishState(validation.errors || []);
  const publish = async () => {
    if (blocked || checking || loadError || !state.canPublish || validation.valid !== true || loading) return;
    setPublishError(false);
    setLoading(true);
    try { await publishCatalog(projectId); message.success('目录已发布'); await load(); }
    catch { setPublishError(true); }
    finally { setLoading(false); }
  };
  if (checking) return <p role="status">正在检查目录并预览价格…</p>;
  if (!loadError && version?.status === 'published') return <Alert type="success" showIcon message={`目录第 ${version.version} 版已发布`} description="当前没有待发布草稿。需要修改顾客可选内容时，请先创建编辑草稿。" action={<Button onClick={() => void load()}>刷新状态</Button>} />;
  if (loadError) return <Alert type="error" showIcon message="发布检查失败" description="尚未确认目录是否可发布，请重试检查。" action={<Button onClick={() => void load()}>重新检查</Button>} />;
  return <Space direction="vertical" style={{ width: '100%' }}>
    {publishError && <Alert type="error" showIcon message="尚未确认发布结果" description="请先重新检查目录状态，再决定是否重试发布。" />}
    <Card size="small" title="生效检查">
      {state.canPublish && validation.valid ? <Alert type="success" showIcon message="目录检查通过，可以发布" /> : <Alert type="error" showIcon message="目录尚未满足发布条件" description={<List size="small" dataSource={state.messages} renderItem={(item) => <List.Item>{item}</List.Item>} />} />}
      <Space wrap style={{ marginTop: 12 }}><Button type="primary" disabled={blocked || !state.canPublish || validation.valid !== true} loading={loading} onClick={publish}>发布当前目录</Button><Button disabled={loading} onClick={() => void load()}>重新检查</Button></Space>
    </Card>
    <Card size="small" title="示例组合价格">
      <p className="project-save-note">按必选项的最少组合试算，不含其他可选加购。实际金额由服务端按顾客所选项目计算。</p>
      {preview ? <Descriptions size="small" column={3} bordered>
        <Descriptions.Item label="普通顾客">{formatCents(preview.store_total_cents)}</Descriptions.Item>
        <Descriptions.Item label="年度会员">{formatCents(preview.member_total_cents)}</Descriptions.Item>
        <Descriptions.Item label="周二会员日">{formatCents(preview.tuesday_total_cents)}</Descriptions.Item>
      </Descriptions> : previewError ? <Alert type="warning" showIcon message="价格预览失败" description="未取得有效金额，不代表项目免费。请重新检查或先修正目录问题。" /> : <Tag>未取得价格预览</Tag>}
    </Card>
  </Space>;
}
