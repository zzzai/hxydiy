import { LayoutGrid, UserRound, UsersRound } from 'lucide-react';
import './customer-bottom-nav.css';

export type CustomerTab = 'projects' | 'technicians' | 'profile';

const tabs = [
  { key: 'projects', label: '选项目', icon: LayoutGrid },
  { key: 'technicians', label: '看技师', icon: UsersRound },
  { key: 'profile', label: '我的', icon: UserRound },
] as const;

export default function CustomerBottomNav({ active, onSelect }: {
  active: CustomerTab;
  onSelect: (tab: CustomerTab) => void;
}) {
  return <nav className="customer-bottom-nav" aria-label="顾客导航">
    <div className="customer-bottom-nav-inner">
      {tabs.map(({ key, label, icon: Icon }) =>
        <button key={key} type="button" className={key === 'technicians' ? 'customer-tab customer-tab-featured' : 'customer-tab'}
          aria-label={label} aria-current={active === key ? 'page' : undefined} onClick={() => onSelect(key)}>
          <Icon size={21} strokeWidth={1.65} aria-hidden="true" /><span>{label}</span>
        </button>
      )}
    </div>
  </nav>;
}
