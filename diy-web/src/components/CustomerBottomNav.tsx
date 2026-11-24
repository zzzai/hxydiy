import { LayoutGrid, UserRound, UsersRound } from 'lucide-react';
import { useLayoutEffect, useRef, type MutableRefObject } from 'react';
import './customer-bottom-nav.css';

export type CustomerTab = 'projects' | 'technicians' | 'profile';
type Glide = { to: CustomerTab; offset: number; scale: number };
export type DockOrigin = { tab: CustomerTab; glide?: Glide };

function relativeGlide(to: CustomerTab, from?: Element | null, target?: Element | null): Glide | undefined {
  const start = from?.getBoundingClientRect();
  const end = target?.getBoundingClientRect();
  if (!start?.width || !end?.width) return;
  return { to, offset: 100 * (start.left - end.left) / end.width, scale: start.width / end.width };
}

const tabs = [
  { key: 'projects', label: '选项目', icon: LayoutGrid },
  { key: 'technicians', label: '看技师', icon: UsersRound },
  { key: 'profile', label: '我的', icon: UserRound },
] as const;

export default function CustomerBottomNav({ active, onSelect, origin }: {
  active: CustomerTab;
  onSelect: (tab: CustomerTab) => void;
  origin: MutableRefObject<DockOrigin | null>;
}) {
  const track = useRef<HTMLDivElement>(null);
  const glass = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const previous = origin.current;
    origin.current = { tab: active };
    const pill = glass.current;
    if (!pill || !previous || previous.tab === active || !pill.animate
        || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    let glide = previous.glide;
    if (glide?.to !== active) {
      // Browser Back has no tab click. Use the matching buttons in the newly visible bar.
      const from = track.current?.querySelector<HTMLElement>(`[data-tab="${previous.tab}"]`);
      glide = relativeGlide(active, from, pill.parentElement);
    }
    if (!glide) return;
    const animation = pill.animate([
      { transform: `translateX(${glide.offset}%) scaleX(${glide.scale})` },
      { transform: 'none' },
    ], { duration: 285, easing: 'cubic-bezier(.24,.8,.26,1)' });
    return () => animation.cancel();
  }, [active, origin]);

  const select = (tab: CustomerTab, button?: HTMLButtonElement) => {
    if (tab === active) return;
    // Capture the moving pill before switching roots, including entry into the native dialog.
    origin.current = { tab: active, glide: relativeGlide(tab, glass.current, button) };
    onSelect(tab);
  };

  return <nav className="customer-bottom-nav" aria-label="顾客导航">
    <div className="customer-bottom-nav-inner" ref={track}>
      {tabs.map(({ key, label, icon: Icon }) =>
        <button key={key} type="button" data-tab={key} className={key === 'technicians' ? 'customer-tab customer-tab-featured' : 'customer-tab'}
          aria-label={label} aria-current={active === key ? 'page' : undefined} onClick={event => select(key, event?.currentTarget)}>
          {active === key && <span ref={glass} aria-hidden="true" className="customer-tab-glass" />}
          <Icon size={21} strokeWidth={1.65} aria-hidden="true" /><span className="customer-tab-label">{label}</span>
        </button>
      )}
    </div>
  </nav>;
}
