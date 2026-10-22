import { useEffect, useState } from 'react';
import { Select, Space, Typography } from 'antd';
import { getStaff, getStoreMasterData } from '../api';

type Props = {
  value?: number;
  onChange: (storeId: number) => void;
};

type StoreOption = { id: number; name: string; store_code: string; status: string };

export default function StoreScopeSelect({ value, onChange }: Props) {
  const staff = getStaff();
  const headquarters = staff?.role === 'admin' && !staff.store_id;
  const [stores, setStores] = useState<StoreOption[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!headquarters) return;
    let active = true;
    setLoading(true);
    void getStoreMasterData({ page: 1, page_size: 100 })
      .then((response) => {
        if (!active) return;
        const items: StoreOption[] = response.data?.items || [];
        setStores(items);
        if (!value && items[0]) onChange(items[0].id);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [headquarters]);

  if (!headquarters) return null;

  return (
    <Space size={6}>
      <Typography.Text type="secondary">操作门店</Typography.Text>
      <Select
        aria-label="选择操作门店"
        style={{ width: 240 }}
        loading={loading}
        value={value}
        placeholder={stores.length ? '选择门店' : '暂无门店'}
        onChange={onChange}
        options={stores.map((store) => ({
          value: store.id,
          label: `${store.name}${store.status === 'open' ? '' : `（${store.status}）`}`,
        }))}
      />
    </Space>
  );
}
