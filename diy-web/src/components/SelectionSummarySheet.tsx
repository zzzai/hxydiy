import { Minus, PencilLine, Plus, Sparkles, Trash2, X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

import { selectionSettlementNote } from '../customerCopy';
import { sheetMotion } from '../motionPresets';
import { formatMoney } from '../domain';
import type {
  ActivePromotion,
  SelectionSummary,
  SelectionSummaryChild,
  SelectionSummaryGroup,
  SelectionTarget,
} from '../selectionSummary';

type Props = {
  open: boolean;
  summary: SelectionSummary;
  promotion: ActivePromotion | null;
  totalCents: number;
  priceLabel: string;
  memberHint: string | null;
  savingCents: number;
  originalHint: string | null;
  realizedSavingCents: number;
  saving: boolean;
  readOnly: boolean;
  positionLabel: string;
  identityLabel: string;
  onClose: () => void;
  onModify: (target: SelectionTarget) => void;
  onRemove: (target: SelectionTarget) => void;
  onQuantityChange: (target: Extract<SelectionTarget, { kind: 'project' | 'local' }>, delta: 1 | -1) => void;
};

function Price({ cents, label, originalPriceCents, memberPriceCents }: {
  cents: number;
  label?: string;
  originalPriceCents: number | null;
  memberPriceCents: number | null;
}) {
  return (
    <div className="selection-sheet-item-price">
      <strong className={label ? 'is-free' : ''}>{label || formatMoney(cents)}</strong>
      {!label && originalPriceCents !== null && <del>门店价 {formatMoney(originalPriceCents)}</del>}
      {!label && memberPriceCents !== null && <span className="selection-sheet-member-price">会员价 {formatMoney(memberPriceCents)}</span>}
    </div>
  );
}

function ItemActions({ target, title, quantity, adjustable, readOnly, onModify, onRemove, onQuantityChange }: {
  target: SelectionTarget;
  title: string;
  quantity: number;
  adjustable: boolean;
  readOnly: boolean;
  onModify: (target: SelectionTarget) => void;
  onRemove: (target: SelectionTarget) => void;
  onQuantityChange: (target: Extract<SelectionTarget, { kind: 'project' | 'local' }>, delta: 1 | -1) => void;
}) {
  if (readOnly) return null;
  return (
    <div className="selection-sheet-item-actions">
      <button type="button" aria-label={`修改${title}`} onClick={() => onModify(target)}><PencilLine size={14} />修改</button>
      {adjustable && (target.kind === 'project' || target.kind === 'local') ? (
        <div className="selection-sheet-stepper" role="group" aria-label={`${title}数量`}>
          <button type="button" aria-label={`减少${title}`} onClick={() => onQuantityChange(target, -1)}><Minus size={14} /></button>
          <span aria-live="polite">{quantity}</span>
          <button type="button" aria-label={`增加${title}`} onClick={() => onQuantityChange(target, 1)}><Plus size={14} /></button>
        </div>
      ) : (
        <button className="remove" type="button" aria-label={`删除${title}`} onClick={() => onRemove(target)}><Trash2 size={14} />删除</button>
      )}
    </div>
  );
}

function ChildLine({ item, readOnly, onModify, onRemove, onQuantityChange }: {
  item: SelectionSummaryChild;
  readOnly: boolean;
  onModify: (target: SelectionTarget) => void;
  onRemove: (target: SelectionTarget) => void;
  onQuantityChange: Props['onQuantityChange'];
}) {
  return (
    <div className="selection-sheet-child">
      <div className="selection-sheet-item-copy">
        <small>加项</small>
        <strong>{item.title}</strong>
        <p>{item.detail}</p>
      </div>
      <div className="selection-sheet-item-side">
        <Price cents={item.priceCents} label={item.priceLabel} originalPriceCents={item.originalPriceCents} memberPriceCents={item.memberPriceCents} />
        <ItemActions target={item.target} title={item.title} quantity={item.quantity} adjustable={false} readOnly={readOnly} onModify={onModify} onRemove={onRemove} onQuantityChange={onQuantityChange} />
      </div>
    </div>
  );
}

function GroupLine({ group, readOnly, onModify, onRemove, onQuantityChange }: {
  group: SelectionSummaryGroup;
  readOnly: boolean;
  onModify: (target: SelectionTarget) => void;
  onRemove: (target: SelectionTarget) => void;
  onQuantityChange: Props['onQuantityChange'];
}) {
  return (
    <article className="selection-sheet-group">
      <div className="selection-sheet-main-line">
        <div className="selection-sheet-item-copy">
          <small>{group.kind === 'tea' ? '到店赠饮' : group.kind === 'local' ? '局部调理' : '服务项目'}</small>
          <strong>{group.title}</strong>
          <p>{group.detail}</p>
        </div>
        <div className="selection-sheet-item-side">
          <Price cents={group.priceCents} label={group.priceLabel} originalPriceCents={group.originalPriceCents} memberPriceCents={group.memberPriceCents} />
          <ItemActions target={group.target} title={group.title} quantity={group.quantity} adjustable={group.kind !== 'tea'} readOnly={readOnly} onModify={onModify} onRemove={onRemove} onQuantityChange={onQuantityChange} />
        </div>
      </div>
      {group.children.map((item) => (
        <ChildLine key={item.key} item={item} readOnly={readOnly} onModify={onModify} onRemove={onRemove} onQuantityChange={onQuantityChange} />
      ))}
    </article>
  );
}

export default function SelectionSummarySheet({
  open,
  summary,
  promotion,
  totalCents,
  priceLabel,
  memberHint,
  savingCents,
  originalHint,
  realizedSavingCents,
  saving,
  readOnly,
  positionLabel,
  identityLabel,
  onClose,
  onModify,
  onRemove,
  onQuantityChange,
}: Props) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus({ preventScroll: true });
    const closeOnEscape = (event: KeyboardEvent) => event.key === 'Escape' && onCloseRef.current();
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="selection-summary-layer" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <motion.section data-motion="selection-sheet" {...sheetMotion} className="selection-summary-sheet" role="dialog" aria-modal="true" aria-labelledby="selection-summary-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="selection-sheet-header">
          <div>
            <strong id="selection-summary-title">{readOnly ? '已提交服务' : '本次待提交'}</strong>
            <span>{summary.totalCount}项</span>
          </div>
          <button ref={closeButtonRef} type="button" aria-label="关闭本次已选" onClick={onClose}><X size={19} /></button>
        </header>

        <div className="selection-sheet-context" aria-label="提交前确认信息">
          <span><small>服务位置</small><strong>{positionLabel}</strong></span>
          <span><small>当前身份</small><strong>{identityLabel}</strong></span>
        </div>

        <div className="selection-sheet-scroll">
          {summary.groups.map((group) => (
            <GroupLine key={group.key} group={group} readOnly={readOnly} onModify={onModify} onRemove={onRemove} onQuantityChange={onQuantityChange} />
          ))}
        </div>

        {promotion && (
          <div className="selection-sheet-promotion">
            <Sparkles size={17} />
            <span><strong>{promotion.label}</strong><small>已计入当前预计金额</small></span>
            <em>-{formatMoney(Math.abs(promotion.amountCents))}</em>
          </div>
        )}

        <footer className="selection-sheet-total" aria-live="polite">
          <div className="selection-sheet-checkout">
            <div className="selection-sheet-breakdown">
              {originalHint && <span><small>门店价</small><del>{originalHint.replace('门店价 ', '')}</del></span>}
              {realizedSavingCents > 0 && <span><small>会员优惠</small><strong>-{formatMoney(realizedSavingCents)}</strong></span>}
              {memberHint && <span><small>办卡后可享</small><strong>{memberHint}</strong></span>}
              {savingCents > 0 && <span><small>预计可省</small><strong>{formatMoney(savingCents)}</strong></span>}
            </div>
            <div className="selection-sheet-payable"><small>{saving ? '正在更新' : priceLabel}</small><span>预计合计</span><strong>{formatMoney(totalCents)}</strong></div>
          </div>
          <p>{selectionSettlementNote(readOnly)}</p>
        </footer>
      </motion.section>
    </div>
  );
}
