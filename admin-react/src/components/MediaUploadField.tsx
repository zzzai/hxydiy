import { useEffect, useState } from 'react';
import { App, Button, Image, Space, Upload } from 'antd';
import { DeleteOutlined, UploadOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import * as qiniu from 'qiniu-js';
import {
  client,
  completeDirectMediaUpload,
  createDirectMediaUpload,
  deleteMedia,
  isDirectMediaUploadUnavailable,
  uploadMedia,
  type DirectMediaUploadGrant,
} from '../api';
import { waitForQiniuUpload } from '../qiniuDirectUpload';

type MediaValue = string | { id?: number; url: string } | undefined;
type RetryableDirectUpload = { file: File; grant: DirectMediaUploadGrant };

export default function MediaUploadField({ value, onChange, purpose = 'general', storeId, requireStoreId = false }: {
  value?: MediaValue;
  onChange?: (value: string) => void;
  purpose?: string;
  storeId?: number;
  requireStoreId?: boolean;
}) {
  const { message } = App.useApp();
  const [uploading, setUploading] = useState(false);
  const [uploadPercent, setUploadPercent] = useState<number>();
  const [previewUrl, setPreviewUrl] = useState<string>();
  const [failedFile, setFailedFile] = useState<File>();
  const [retryableDirectUpload, setRetryableDirectUpload] = useState<RetryableDirectUpload>();
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
  const upload = async (file: File) => {
    setUploading(true);
    setUploadPercent(undefined);
    let grant = retryableDirectUpload?.file === file ? retryableDirectUpload.grant : undefined;
    try {
      if (!grant) {
        try {
          grant = (await createDirectMediaUpload(file, purpose, storeId)).data;
        } catch (error) {
          if (isDirectMediaUploadUnavailable(error)) {
            const response = await uploadMedia(file, purpose, storeId);
            onChange?.(response.data.url);
            setFailedFile(undefined);
            return response.data;
          }
          throw error;
        }
      }
      await waitForQiniuUpload(
        qiniu.upload(file, grant.key, grant.upload_token, { fname: file.name, mimeType: file.type }),
        setUploadPercent,
      );
      const response = await completeDirectMediaUpload(grant.ticket);
      onChange?.(response.data.url);
      setFailedFile(undefined);
      setRetryableDirectUpload(undefined);
      return response.data;
    } catch (error) {
      setFailedFile(file);
      if (grant) setRetryableDirectUpload({ file, grant });
      message.error(error instanceof Error ? error.message : '图片上传失败');
      throw error;
    } finally {
      setUploading(false);
      setUploadPercent(undefined);
    }
  };
  const props: UploadProps = {
    accept: 'image/jpeg,image/png,image/webp,image/gif',
    showUploadList: false,
    maxCount: 1,
    customRequest: async ({ file, onError, onSuccess }) => {
      try {
        const media = await upload(file as File);
        onSuccess?.(media);
      } catch (error) {
        onError?.(error as Error);
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
      <Upload {...props}><Button icon={<UploadOutlined />} loading={uploading} disabled={uploading || (requireStoreId && !storeId)}>{uploading && uploadPercent !== undefined ? `上传中 ${Math.round(uploadPercent)}%` : (url ? '替换图片' : '上传图片')}</Button></Upload>
      {failedFile && <Button loading={uploading} onClick={() => void upload(failedFile)}>重试上传</Button>}
      {mediaId && <Button danger type="text" icon={<DeleteOutlined />} onClick={async () => { await deleteMedia(mediaId); onChange?.(''); message.success('图片已删除'); }}>删除</Button>}
    </Space>
  </Space>;
}
