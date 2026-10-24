import { Button, Collapse, Form, Input, InputNumber, Select, Space, Tag } from 'antd';
import type { FormInstance } from 'antd';
import MediaUploadField from '../MediaUploadField';
import { moveProjectDetailModule } from '../../projectContent';

const CAT_MAP: Record<string, string> = { bath: '泡脚沐足', balance: '推拿', care: '精油SPA', small: '养生小项', 'local-strength': '局部调理', kit: '功夫调理', tea: '茶饮' };

export default function ProjectBasicFields({ form, editing, onDirty }: { form: FormInstance; editing: any | null; onDirty?: () => void }) {
  const category = Form.useWatch('category', form);
  const selectedStoreId = Form.useWatch('store_id', form);
  const mediaStoreId = editing?.store_id || selectedStoreId;
  const priceRule = { validator: (_: unknown, value: number | null | undefined) => value === null ? Promise.reject(new Error('请填写金额，免费请填 0')) : Promise.resolve() };
  return <div className="project-editor-layout"><div className="project-editor-fields">
    <section className="project-editor-section" aria-labelledby="project-content-heading">
      <h3 id="project-content-heading">项目内容</h3><p>名称、主图和简介会展示给顾客。</p>
      <div className="project-field-grid">
        <Form.Item name="name" label="项目名称" rules={[{ required: true, whitespace: true, message: '请填写项目名称' }, { max: 64, message: '项目名称最多 64 个字' }]}><Input maxLength={64} showCount /></Form.Item>
        <Form.Item name="category" label="项目分类" initialValue="bath"><Select options={Object.entries(CAT_MAP).map(([value, label]) => ({ value, label }))} /></Form.Item>
        <Form.Item name="duration_min" label="服务时长（分钟）"><InputNumber min={0} precision={0} /></Form.Item>
        <Form.Item name="tags_text" label="顾客可见标签"><Input placeholder="多个标签用逗号分隔" /></Form.Item>
      </div>
      <Form.Item name="image_url" label="项目主图"><MediaUploadField purpose="project_cover" storeId={mediaStoreId} requireStoreId removeFromFormOnly /></Form.Item>
      <Form.Item name="summary" label="项目简介" rules={[{ max: 512, message: '项目简介最多 512 个字' }]}><Input.TextArea maxLength={512} showCount rows={3} placeholder="说明服务内容和包含项目" /></Form.Item>
    </section>
    <section className="project-editor-section" aria-labelledby="project-prices-heading">
      <h3 id="project-prices-heading">项目价格</h3><p>统一按元填写。会员和活动是否适用仍由服务端判断。</p>
      <div className="project-price-grid">
        <Form.Item name="store_price" label="门店价（元）" rules={[priceRule]}><InputNumber min={0} precision={2} /></Form.Item>
        <Form.Item name="member_price" label="会员价（元）" rules={[priceRule]}><InputNumber min={0} precision={2} /></Form.Item>
        <Form.Item name="group_price" label="团购价（元）" rules={[priceRule]}><InputNumber min={0} precision={2} /></Form.Item>
      </div>
    </section>
    <section className="project-editor-section" aria-labelledby="project-display-heading">
      <h3 id="project-display-heading">展示设置</h3>
      <div className="project-field-grid">
        <Form.Item name="independently_visible" label="在顾客菜单中展示" initialValue={true}><Select options={[{ value: true, label: '独立展示' }, { value: false, label: '仅作为其他项目的加选项' }]} /></Form.Item>
        <Form.Item name="publication_status" label="项目上架状态" initialValue="published"><Select options={[{ value: 'draft', label: '草稿，不向顾客展示' }, { value: 'published', label: '已发布' }, ...(!['draft', 'published'].includes(editing?.publication_status || 'published') ? [{ value: editing.publication_status, label: ({ candidate: '待审核', inactive: '已停用', archived: '总部强制下线' } as Record<string, string>)[editing.publication_status] || '当前状态', disabled: true }] : [])]} /></Form.Item>
        <Form.Item name="display_order" label="菜单排序" initialValue={0}><InputNumber min={0} precision={0} /></Form.Item>
        <Form.Item name="category_mark" label="分类标识"><Select allowClear options={['茶', '清', '泡', '调', '补', '养', '辅'].map((value) => ({ value, label: value }))} /></Form.Item>
      </div>
      <Form.Item name="code" label="项目编码" extra="用于关联项目，已有项目的编码不可更改。" rules={[{ required: true, whitespace: true, message: '请填写项目编码' }, { max: 32, message: '项目编码最多 32 个字符' }]}><Input maxLength={32} disabled={!!editing} /></Form.Item>
    </section>
    <Collapse ghost items={[{ key: 'details', label: '详情内容与历史选项', forceRender: true, children: <>
    <div className="admin-subtitle">详情内容</div>
    <Form.List name="detail_modules">
      {(fields, { add, remove }) => <>
        {fields.map(({ key, name, ...restField }) => <div key={key} draggable onDragStart={(event) => event.dataTransfer.setData('text/plain', String(name))} onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
          event.preventDefault();
          const from = Number(event.dataTransfer.getData('text/plain'));
          const detailModules = form.getFieldValue('detail_modules') || [];
          form.setFieldValue('detail_modules', moveProjectDetailModule(detailModules, from, name));
          onDirty?.();
        }} style={{ cursor: 'grab' }}>
          <Space align="start" style={{ display: 'flex', width: '100%' }}>
            <span aria-label="拖拽排序" style={{ paddingTop: 5, color: '#84928e' }}>⠿</span>
            <Form.Item {...restField} name={[name, 'type']} initialValue="text"><Select style={{ width: 100 }} options={[{ value: 'text', label: '文字' }, { value: 'image', label: '图片' }, { value: 'highlight', label: '亮点' }]} /></Form.Item>
            <Form.Item {...restField} name={[name, 'title']}><Input placeholder="标题" /></Form.Item>
            <Form.Item noStyle shouldUpdate={(prev, current) => prev.detail_modules?.[name]?.type !== current.detail_modules?.[name]?.type}>
              {({ getFieldValue }) => getFieldValue(['detail_modules', name, 'type']) === 'image'
                ? <Form.Item {...restField} name={[name, 'body']} label="图片"><MediaUploadField purpose="project_detail" storeId={mediaStoreId} requireStoreId removeFromFormOnly /></Form.Item>
                : <Form.Item {...restField} name={[name, 'body']}><Input placeholder="内容" /></Form.Item>}
            </Form.Item>
            <Button danger type="text" onClick={() => remove(name)}>删除</Button>
          </Space>
        </div>)}
        <Button type="dashed" onClick={() => add({ type: 'text' })} block>增加详情模块</Button>
      </>}
    </Form.List>
    {category === 'bath' && <>
      <div className="admin-subtitle">兼容 DIY 选项</div>
      <Form.List name="diy_options">
        {(fields, { add, remove }) => <>
          {fields.map(({ key, name, ...restField }) => <Space key={key} align="start" style={{ display: 'flex', width: '100%' }}>
            <Form.Item {...restField} name={[name, 'label']}><Input placeholder="选项名称" /></Form.Item>
            <Form.Item {...restField} name={[name, 'note']}><Input placeholder="说明" /></Form.Item>
            <Button danger type="text" onClick={() => remove(name)}>删除</Button>
          </Space>)}
          <Button type="dashed" onClick={() => add()} block>增加兼容选项</Button>
        </>}
      </Form.List>
    </>}
    </> }]} />
  </div><aside className="project-display-preview" aria-label="顾客展示摘要预览">
    <span className="project-preview-label">顾客展示摘要</span>
    <Form.Item noStyle shouldUpdate>{({ getFieldsValue }) => {
      const values = getFieldsValue(true);
      return <>
        <h3>{values.name || '项目名称'}</h3>
        <p>{values.summary || '填写简介后，可在这里核对顾客看到的内容。'}</p>
        <Space wrap>{String(values.tags_text || '').split(/[，,]/).filter(Boolean).map((tag: string, index: number) => <Tag key={index}>{tag}</Tag>)}</Space>
        {values.duration_min != null && <p>{values.duration_min} 分钟</p>}
        <dl>{[['store_price', '门店价'], ['member_price', '会员价'], ['group_price', '团购价']].map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{typeof values[key] === 'number' ? `¥${values[key].toFixed(2)}` : '未配置'}</dd></div>)}</dl>
        <small>仅预览当前填写的展示内容。加选和优惠后的金额请到“检查与发布”核对。</small>
      </>;
    }}</Form.Item>
  </aside></div>;
}
