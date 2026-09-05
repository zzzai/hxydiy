import { useEffect, useState } from 'react';
import { App, Button, Image, Space, Upload } from 'antd';
import { DeleteOutlined, UploadOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { client, deleteMedia, uploadMedia } from '../api';

type MediaValue = string | { id?: number; url: string } | undefined;

export default function MediaUploadField({ value, onChange, purpose = 'general', storeId, requireStoreId = false }: {
  value?: MediaValue;
  onChange?: (value: string) => void;
  purpose?: string;
  storeId?: number;
  requireStoreId?: boolean;
}) {
  const { message } = App.useApp();
  const [uploading, setUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string>();
  const url = typeof value === 'string' ? value : value?.url;
  const mediaId = typeof value === 'object' ? value?.id : Number(url?.match(/\/media\/(\d+)\//)?.[1]) || undefined;
  useEffect(() => {
    if (!url || url.startsWith('data:') || url.startsWith('blob:') || /^https?:\/\//.test(url)) {
      setPreviewUrl(url);
      return;
    }
    let active = true;
    client.get(url, { responseType: 'blob' }).then((response) => {
      if (active) setPreviewUrl(URL.createObjectURL(response.data));
    }).catch(() => { if (active) setPreviewUrl(undefined); });
    return () => { active = false; };
  }, [url]);
  const props: UploadProps = {
    accept: 'image/jpeg,image/png,image/webp,image/gif',
    showUploadList: false,
    maxCount: 1,
    customRequest: async ({ file, onError, onSuccess }) => {
      setUploading(true);
      try {
        const response = await uploadMedia(file as File, purpose, storeId);
        const media = response.data;
        onChange?.(media.url);
        onSuccess?.(media);
      } catch (error) {
        message.error(error instanceof Error ? error.message : '图片上传失败');
        onError?.(error as Error);
      } finally {
        setUploading(false);
      }
    },
    beforeUpload: (file) => {
      if (!file.type.startsWith('image/')) {
        message.error('请选择图片文件');
        return Upload.LIST_IGNORE;
      }
      if (file.size > 5 * 1024 * 1024) {
        message.error('图片不能超过 5MB');
        return Upload.LIST_IGNORE;
      }
      return true;
    },
  };
  return <Space direction="vertical" size={8}>
    {previewUrl && <Image src={previewUrl} width={120} height={90} style={{ objectFit: 'cover' }} />}
    <Space>
      <Upload {...props}><Button icon={<UploadOutlined />} loading={uploading} disabled={requireStoreId && !storeId}>{url ? '替换图片' : '上传图片'}</Button></Upload>
      {mediaId && <Button danger type="text" icon={<DeleteOutlined />} onClick={async () => { await deleteMedia(mediaId); onChange?.(''); message.success('图片已删除'); }}>删除</Button>}
    </Space>
  </Space>;
}
