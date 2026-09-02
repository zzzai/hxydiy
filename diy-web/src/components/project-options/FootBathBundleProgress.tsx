import type { PricingPreview } from '../../domain';
import { footBathBundleCopy } from '../../customerCopy';

export default function FootBathBundleProgress({ preview, selectedParts = [], isMember = false }: { preview: PricingPreview; selectedParts?: string[]; isMember?: boolean }) {
  const copy = footBathBundleCopy(preview, selectedParts, isMember);
  return <div className={`mini-promotion ${preview.qualified ? 'qualified' : ''}`} role="status">
    <div><strong>{copy.title}</strong><small>{copy.detail}</small></div>
    <span>{copy.value}</span>
  </div>;
}
