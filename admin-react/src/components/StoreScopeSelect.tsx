import { useEffect, useState } from 'react';
import { Select, Space, Typography } from 'antd';
import { getStaff, getStoreMasterData } from '../api';

type Props = {
  value?: number;
  onChange: (storeId: number) => void;
};

type StoreOption = { id: number; name: string; store_code: string; status: string };

const STORE_SCOPE_STORAGE_KEY = 'hxy:admin:store-scope';

function readSavedStoreId(): number | undefined {
  try {
    const raw = window.localStorage.getItem(STORE_SCOPE_STORAGE_KEY);
    const parsed = raw ? Number(raw) : NaN;
    return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
  } catch { return undefined; }
}

function persistStoreId(storeId: number) {
  try { window.localStorage.setItem(STORE_SCOPE_STORAGE_KEY, String(storeId)); } catch { /* storage may be disabled */ }
}

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
        if (!value) {
          const saved = readSavedStoreId();
          const next = items.find((store) => store.id === saved)?.id ?? items[0]?.id;
          if (next) onChange(next);
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [headquarters]);

  const handleChange = (storeId: number) => {
    persistStoreId(storeId);
    onChange(storeId);
  };

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
        onChange={handleChange}
        options={stores.map((store) => ({
          value: store.id,
          label: `${store.name}${store.status === 'open' ? '' : `（${store.status}）`}`,
        }))}
      />
    </Space>
  );
}
