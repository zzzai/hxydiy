import { Button, Form, Input, InputNumber, Select, Space } from 'antd';
import type { FormInstance } from 'antd';
import MediaUploadField from '../MediaUploadField';

const CAT_MAP: Record<string, string> = { bath: '泡脚沐足', balance: '推拿', care: '精油SPA', small: '养生小项', 'local-strength': '局部调理', kit: '功夫调理', tea: '茶饮' };

export default function ProjectBasicFields({ form, editing }: { form: FormInstance; editing: any | null }) {
  const category = Form.useWatch('category', form);
  return <Space style={{ width: '100%' }} direction="vertical">
    <Space wrap><Form.Item name="code" label="编码" rules={[{ required: true }]}><Input disabled={!!editing} /></Form.Item>
      <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item></Space>
    <Space wrap><Form.Item name="category" label="分类" initialValue="bath"><Select options={Object.entries(CAT_MAP).map(([value, label]) => ({ value, label }))} /></Form.Item>
      <Form.Item name="category_mark" label="标识"><Select allowClear options={['茶', '清', '泡', '调', '补', '养', '辅'].map((value) => ({ value, label: value }))} /></Form.Item></Space>
    <Space wrap><Form.Item name="duration_min" label="时长(分)"><InputNumber min={0} /></Form.Item>
      <Form.Item name="display_order" label="展示顺序" initialValue={0}><InputNumber min={0} /></Form.Item>
      <Form.Item name="publication_status" label="状态" initialValue="published"><Select options={[{ value: 'draft', label: '草稿' }, { value: 'published', label: '已发布' }]} /></Form.Item></Space>
    <Space wrap><Form.Item name="store_price" label="门店价(元)"><InputNumber min={0} /></Form.Item>
      <Form.Item name="member_price" label="会员价(元)"><InputNumber min={0} /></Form.Item>
      <Form.Item name="group_price" label="团购价(元)"><InputNumber min={0} /></Form.Item></Space>
    <Form.Item name="image_url" label="主图"><MediaUploadField purpose="project_cover" /></Form.Item>
    <Form.Item name="tags_text" label="标签"><Input placeholder="多个标签用逗号分隔" /></Form.Item>
    <Form.Item name="summary" label="简介"><Input.TextArea rows={2} /></Form.Item>
    <div className="admin-subtitle">详情模块</div>
    <Form.List name="detail_modules">
      {(fields, { add, remove }) => <>
        {fields.map(({ key, name, ...restField }) => <Space key={key} align="start" style={{ display: 'flex', width: '100%' }}>
          <Form.Item {...restField} name={[name, 'type']} initialValue="text"><Select style={{ width: 100 }} options={[{ value: 'text', label: '文字' }, { value: 'image', label: '图片' }, { value: 'highlight', label: '亮点' }]} /></Form.Item>
          <Form.Item {...restField} name={[name, 'title']}><Input placeholder="标题" /></Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, current) => prev.detail_modules?.[name]?.type !== current.detail_modules?.[name]?.type}>
            {({ getFieldValue }) => getFieldValue(['detail_modules', name, 'type']) === 'image'
              ? <Form.Item {...restField} name={[name, 'body']} label="图片"><MediaUploadField purpose="project_detail" /></Form.Item>
              : <Form.Item {...restField} name={[name, 'body']}><Input placeholder="内容" /></Form.Item>}
          </Form.Item>
          <Button danger type="text" onClick={() => remove(name)}>删除</Button>
        </Space>)}
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
  </Space>;
}
