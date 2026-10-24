import { useEffect, useState } from 'react';
import { Button, Select, Space, Typography } from 'antd';
import { requestErrorMessage } from '../requestError';
import { getStaff, getStoreMasterData } from '../api';

type Props = {
  value?: number;
  disabled?: boolean;
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

export default function StoreScopeSelect({ value, onChange, disabled = false }: Props) {
  const staff = getStaff();
  const headquarters = staff?.role === 'admin' && !staff.store_id;
  const [stores, setStores] = useState<StoreOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!headquarters) return;
    let active = true;
    setLoading(true); setError('');
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
      .catch(error => { if (active) { setStores([]); setError(requestErrorMessage(error)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [headquarters, attempt]);

  useEffect(() => { if (value) persistStoreId(value); }, [value]);

  const handleChange = (storeId: number) => {
    onChange(storeId);
  };

  if (!headquarters) return null;

  return (
    <Space size={6} wrap>
      <Typography.Text type="secondary">操作门店</Typography.Text>
      <Select
        aria-label="选择操作门店"
        style={{ width: 240 }}
        loading={loading}
        disabled={disabled || loading}
        value={value}
        placeholder={error ? '门店加载失败' : stores.length ? '选择门店' : '暂无可用门店'}
        onChange={handleChange}
        options={stores.map((store) => ({
          value: store.id,
          label: `${store.name}${store.status === 'open' ? '' : `（${store.status}）`}`,
        }))}
      />
      {error && <><Typography.Text type="danger">{error}</Typography.Text><Button size="small" disabled={disabled || loading} onClick={() => setAttempt(n => n + 1)}>重试门店列表</Button></>}
    </Space>
  );
}
