import { useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, List, Space, Tag, message } from 'antd';
import { getOptionGroups, previewCatalogPrice, publishCatalog, validateCatalogPublication } from '../../api';
import { catalogPublishState, formatCents, nextTuesdayIso, previewChoiceIds } from '../../catalogOptions';

const STORE_TIMEZONE = 'Asia/Shanghai';

export default function CatalogPublishPanel({ projectId }: { projectId: number }) {
  const [validation, setValidation] = useState<any>({ valid: false, errors: [] });
  const [preview, setPreview] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const load = async () => {
    const [check, groups] = await Promise.all([validateCatalogPublication(projectId), getOptionGroups(projectId)]);
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
      setPreview({
        store_total_cents: store.data?.total_cents,
        member_total_cents: member.data?.total_cents,
        tuesday_total_cents: tuesday.data?.total_cents,
      });
    } catch { setPreview(null); }
  };
  useEffect(() => { void load(); }, [projectId]);
  const state = catalogPublishState(validation.errors || []);
  const publish = async () => {
    setLoading(true);
    try { await publishCatalog(projectId); message.success('目录已发布'); await load(); }
    finally { setLoading(false); }
  };
  return <Space direction="vertical" style={{ width: '100%' }}>
    <Card size="small" title="发布门禁">
      {state.canPublish && validation.valid ? <Alert type="success" showIcon message="目录检查通过，可以发布" /> : <Alert type="error" showIcon message="目录尚未满足发布条件" description={<List size="small" dataSource={state.messages} renderItem={(item) => <List.Item>{item}</List.Item>} />} />}
      <Button type="primary" disabled={!state.canPublish || validation.valid !== true} loading={loading} onClick={publish} style={{ marginTop: 12 }}>发布当前目录</Button>
    </Card>
    <Card size="small" title="价格预览">
      {preview ? <Descriptions size="small" column={3} bordered>
        <Descriptions.Item label="普通顾客">{formatCents(preview.store_total_cents)}</Descriptions.Item>
        <Descriptions.Item label="年度会员">{formatCents(preview.member_total_cents)}</Descriptions.Item>
        <Descriptions.Item label="周二会员日">{formatCents(preview.tuesday_total_cents)}</Descriptions.Item>
      </Descriptions> : <Tag>暂无可预览目录</Tag>}
    </Card>
  </Space>;
}
