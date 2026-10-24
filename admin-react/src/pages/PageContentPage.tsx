import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Empty, Form, Input, List, Modal, Space, Spin, Switch, Tabs, Tag, Typography } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { getStaff, getPageContent, getPageContentVersions, rollbackPageContent, updatePageContent } from '../api';
import { hasCapability } from '../core/auth/capabilities';
import StoreScopeSelect from '../components/StoreScopeSelect';
import MediaUploadField from '../components/MediaUploadField';
import { pageContentPayload, pageContentToForm, type PageContentForm } from '../pageContentForm';
import { requestErrorMessage } from '../requestError';
import './page-content.css';

type Version = { id: number; version_no: number; title?: string; created_by?: string; created_at?: string };

export default function PageContentPage() {
  const { message, modal } = App.useApp();
  const staff = getStaff();
  const canEdit = hasCapability(staff?.role, 'manage_catalog_master', staff?.store_id);
  const [form] = Form.useForm<PageContentForm>();
  const [storeId, setStoreId] = useState<number | undefined>(staff?.store_id || undefined);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [savedPublished, setSavedPublished] = useState(false);
  const [versionOpen, setVersionOpen] = useState(false);
  const [versionLoading, setVersionLoading] = useState(false);
  const [versionError, setVersionError] = useState('');
  const [versions, setVersions] = useState<Version[]>([]);
  const generation = useRef(0);
  const versionGeneration = useRef(0);
  const busy = useRef(false);
  const watched = Form.useWatch([], form) as PageContentForm | undefined;

  const load = useCallback(async () => {
    if (!canEdit || !storeId) return;
    const ticket = ++generation.current;
    setLoading(true); setLoaded(false); setLoadError(''); setSaveError('');
    try {
      const { data } = await getPageContent('diy-home', storeId);
      if (ticket !== generation.current) return;
      if (data.store_id !== storeId) { setLoadError('返回的内容不属于当前门店，请重新加载。'); return; }
      let values: PageContentForm;
      try { values = pageContentToForm(data); }
      catch (error) { setLoadError((error as Error).message); return; }
      form.resetFields(); form.setFields(Object.entries(values).map(([name, value]) => ({ name, value })));
      setSavedPublished(values.published); setDirty(false); setLoaded(true);
    } catch (error) { if (ticket === generation.current) setLoadError(requestErrorMessage(error)); }
    finally { if (ticket === generation.current) setLoading(false); }
  }, [canEdit, storeId, form]);

  useEffect(() => {
    setVersionOpen(false); setVersions([]); setVersionError(''); versionGeneration.current++;
    void load();
    return () => { generation.current++; versionGeneration.current++; };
  }, [load]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const discardThen = (action: () => void) => {
    if (busy.current) return;
    if (!dirty) { action(); return; }
    modal.confirm({ title: '当前修改尚未保存', content: '继续后将丢弃本页未保存的修改，已保存内容不受影响。', okText: '放弃修改并继续', cancelText: '继续编辑', onOk: action });
  };

  const openVersions = async () => {
    if (!storeId || busy.current) return;
    const ticket = ++versionGeneration.current;
    setVersionOpen(true); setVersionLoading(true); setVersionError(''); setVersions([]);
    try {
      const response = await getPageContentVersions('diy-home', storeId);
      if (ticket === versionGeneration.current) setVersions(response.data?.items || []);
    } catch (error) { if (ticket === versionGeneration.current) setVersionError(requestErrorMessage(error)); }
    finally { if (ticket === versionGeneration.current) setVersionLoading(false); }
  };

  const rollback = async (versionId: number) => {
    if (busy.current || !storeId) return;
    busy.current = true; setSaving(true); setVersionError('');
    try {
      await rollbackPageContent(versionId, 'diy-home', storeId);
      message.success('历史内容已恢复并生效'); setVersionOpen(false); await load();
    } catch (error) { setVersionError(requestErrorMessage(error)); }
    finally { busy.current = false; setSaving(false); }
  };

  const save = async () => {
    if (busy.current || !storeId || !loaded) return;
    busy.current = true; setSaving(true); setSaveError('');
    try {
      const payload = pageContentPayload(form.getFieldsValue(true));
      await updatePageContent('diy-home', payload, storeId);
      setSavedPublished(payload.published); setDirty(false);
      message.success(payload.published ? '本店页面内容已保存并生效' : '配置已保存，顾客端使用默认内容');
    } catch (error) { setSaveError(requestErrorMessage(error)); }
    finally { busy.current = false; setSaving(false); }
  };

  if (!canEdit) return <Alert type="info" showIcon message="当前账号没有页面内容维护权限" description="请使用具备页面内容权限的管理账号。" />;

  const removeRow = (remove: (index: number) => void, index: number) => modal.confirm({
    title: '从配置中移除这项内容？', content: '保存后才会更新配置，不会删除原图片文件。', okText: '移除', cancelText: '保留',
    onOk: () => { remove(index); setDirty(true); },
  });
  const values: PageContentForm = watched || form.getFieldsValue(true) as PageContentForm;

  return <section className="page-content-workspace">
    <div className="page-content-heading"><div><h1>顾客页面内容</h1><p>按门店维护推荐文案与品牌素材，先核对，再生效。</p></div><Space wrap>
      <StoreScopeSelect value={storeId} disabled={saving || loading || versionLoading} onChange={id => discardThen(() => setStoreId(id))} />
      <Button disabled={!loaded || saving} onClick={() => void openVersions()}>发布记录</Button>
      <Button icon={<ReloadOutlined />} disabled={!storeId || saving || loading} onClick={() => discardThen(() => void load())}>重新加载</Button>
    </Space></div>
    {!storeId && <Empty description="请先选择操作门店" />}
    {loading && <div className="page-content-loading"><Spin /><p>正在读取该门店的页面内容…</p></div>}
    {loadError && <Alert type="error" showIcon message="页面内容未能加载" description={loadError} action={<Button onClick={() => void load()}>重新加载</Button>} />}
    {loaded && !loading && <Form form={form} layout="vertical" disabled={saving} onFinish={() => void save()} onValuesChange={() => { setDirty(true); setSaveError(''); }}>
      <div className="page-content-grid"><Card className="page-content-fields" bordered={false}>
        {saveError && <Alert type="error" showIcon message="本次保存未完成，填写内容已保留" description={saveError} style={{ marginBottom: 20 }} />}
        <Tabs items={[
          { key: 'home', label: '首页文案', forceRender: true, children: <>
            <h2>门店推荐</h2><p className="page-content-hint">文案按推荐位顺序对应现有项目；项目顺序、配图、价格和跳转保持原设置。留空时沿用项目默认文案，精油 SPA 标题仍使用项目名称。</p>
            <Form.List name="promo_banners">{(fields, { add, remove, move }) => <>
              {fields.map((field, index) => <section className="page-content-row" key={field.key}>
                <div className="page-content-row-heading"><strong>推荐位 {index + 1}</strong><Space><Button size="small" disabled={index === 0 || saving} onClick={() => { move(index, index - 1); setDirty(true); }}>上移</Button><Button size="small" danger onClick={() => removeRow(remove, index)}>移除</Button></Space></div>
                <div className="page-content-input-grid"><Form.Item name={[field.name, 'eyebrow']} label="推荐角标"><Input placeholder="例如：门店推荐" /></Form.Item><Form.Item name={[field.name, 'title']} label="推荐标题"><Input placeholder="留空沿用项目名称" /></Form.Item></div>
              </section>)}
              <Button icon={<PlusOutlined />} onClick={() => { add({ eyebrow: '', title: '' }); setDirty(true); }}>添加推荐位文案</Button>
            </>}</Form.List>
            <section className="page-content-section"><h2>到店礼提示</h2><p className="page-content-hint">只修改顾客看到的提示文字，不发券、不改变优惠券领取资格。</p>
              <Form.Item name={['coupon_prompt', 'title']} label="提示标题"><Input /></Form.Item>
              <Form.Item name={['coupon_prompt', 'body']} label="提示说明"><Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} /></Form.Item>
            </section>
          </> },
          { key: 'materials', label: '茶饮与品牌素材', forceRender: true, children: <>
            <Alert type="info" showIcon message="这里维护品牌素材" description="当前顾客首页尚未展示这两组素材；保存不会在首页新增茶饮或品牌故事板块。" style={{ marginBottom: 20 }} />
            <h2>茶饮素材</h2><Form.List name="tea_options">{(fields, { add, remove }) => <>
              {fields.map((field, index) => <section className="page-content-row" key={field.key}>
                <div className="page-content-row-heading"><strong>茶饮 {index + 1}</strong><Button size="small" danger onClick={() => removeRow(remove, index)}>移除</Button></div>
                <div className="page-content-input-grid"><Form.Item name={[field.name, 'name']} label="茶饮名称" rules={[{ required: true, whitespace: true, message: '请填写茶饮名称' }]}><Input /></Form.Item><Form.Item name={[field.name, 'note']} label="一句话描述"><Input /></Form.Item></div>
                <Form.Item name={[field.name, 'description']} label="素材说明"><Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} /></Form.Item>
                <Form.Item name={[field.name, 'image_url']} label="配图"><MediaUploadField purpose="page_content" storeId={storeId} requireStoreId removeFromFormOnly /></Form.Item>
              </section>)}
              <Button icon={<PlusOutlined />} onClick={() => { add({ name: '', note: '', description: '', image_url: '' }); setDirty(true); }}>添加茶饮素材</Button>
            </>}</Form.List>
            <section className="page-content-section"><h2>品牌故事素材</h2>
              <Form.Item name={['brand_story', 'title']} label="标题"><Input /></Form.Item>
              <Form.Item name={['brand_story', 'body']} label="正文"><Input.TextArea autoSize={{ minRows: 4, maxRows: 10 }} /></Form.Item>
              <Form.Item name={['brand_story', 'image_url']} label="配图"><MediaUploadField purpose="page_content" storeId={storeId} requireStoreId removeFromFormOnly /></Form.Item>
            </section>
          </> },
          { key: 'settings', label: '生效设置', forceRender: true, children: <>
            <h2>当前门店的页面配置</h2><p className="page-content-hint">标题用于识别配置与发布记录；当前顾客首页标题及副标题沿用现有页面设计。</p>
            <Form.Item name="title" label="配置标题" rules={[{ required: true, whitespace: true, message: '请填写配置标题' }]}><Input /></Form.Item>
            <Form.Item name="subtitle" label="配置副标题"><Input /></Form.Item>
            <Form.Item name="published" label="使用本店页面内容" valuePropName="checked"><Switch checkedChildren="启用" unCheckedChildren="停用" /></Form.Item>
            <Alert type={savedPublished && !values.published ? 'warning' : 'info'} showIcon message={values.published ? '保存后更新本店顾客端内容，并保留发布记录。' : '保存后顾客端使用默认内容，本店配置仍保留。'} description="此处没有独立的线上草稿。尚未准备好的修改，请先留在编辑页核对，不要误以为关闭开关会保留线上旧版。" />
          </> },
        ]} />
      </Card><aside className="page-content-preview">
        <div className="page-content-preview-heading"><strong>文案预览</strong><Tag color={dirty ? 'gold' : 'green'}>{dirty ? '尚未保存' : '已保存'}</Tag></div>
        <p className="page-content-hint">仅预览文字排布，不模拟项目价格或顾客资格。</p>
        {(values.promo_banners || []).map((row, index) => <div className="page-content-promo" key={index}><small>{String(row.eyebrow || '默认推荐角标')}</small><strong>{String(row.title || '沿用项目名称')}</strong></div>)}
        <div className="page-content-promo page-content-gift"><small>到店礼提示</small><strong>{String(values.coupon_prompt?.title || '默认提示标题')}</strong><p>{String(values.coupon_prompt?.body || '沿用默认提示说明')}</p></div>
        <p className="page-content-hint">{values.published ? '保存后对当前门店生效。' : '当前选择为停用，保存后顾客端显示默认内容。'}</p>
      </aside></div>
      <div className="page-content-savebar"><span>{dirty ? '有未保存的修改' : savedPublished ? '本店内容已启用' : '当前使用默认内容'}</span><Button type="primary" htmlType="submit" loading={saving}>{values.published ? '保存并生效' : '保存配置（使用默认内容）'}</Button></div>
    </Form>}
    <Modal title="本店发布记录" open={versionOpen} onCancel={() => { if (!busy.current) { versionGeneration.current++; setVersionOpen(false); } }} footer={<Button disabled={saving} onClick={() => { versionGeneration.current++; setVersionOpen(false); }}>关闭</Button>} width={680}>
      {versionError ? <Alert type="error" showIcon message="发布记录操作未完成" description={versionError} action={<Button disabled={saving} onClick={() => void openVersions()}>重新加载</Button>} /> : <List loading={versionLoading} dataSource={versions} locale={{ emptyText: '本店还没有发布记录。启用内容并保存后，会生成记录。' }} renderItem={version => <List.Item actions={[<Button key="restore" size="small" disabled={saving} onClick={() => modal.confirm({ title: `恢复第 ${version.version_no} 版并立即生效？`, content: '将替换本店当前配置并新增发布记录；未保存的修改会被丢弃，其他门店不受影响。', okText: '恢复并生效', cancelText: '取消', onOk: () => rollback(version.id) })}>恢复此版</Button>]}><List.Item.Meta title={`第 ${version.version_no} 版 · ${version.title || '未命名配置'}`} description={`${version.created_by || '系统'} · ${version.created_at?.slice(0, 19).replace('T', ' ') || '时间未记录'}`} /></List.Item>} />}
    </Modal>
  </section>;
}
