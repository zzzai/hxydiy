# Selection Summary Stepper Design QA

- Source visual truth: `C:\Users\gaoji\AppData\Local\Temp\codex-clipboard-382133fd-b170-4dc0-b403-4e9866ba88ef.png`
- Implementation screenshot: `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\.workbuddy\tmp\selection-stepper-390x844.png`
- Side-by-side comparison: `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\.workbuddy\tmp\selection-stepper-comparison.png`
- Viewport: 390 × 844
- State: “已选项目”底部弹层打开；草本泡脚 + 3 个局部调理；泡脚组合减免生效

## Full-view comparison evidence

The implementation preserves the reference sheet height, white surface, fixed header, internal scrolling, promotion card, expected-total block, and persistent bottom submit bar. The requested intentional change replaces each service row's red delete action with a compact green `− 1 +` control while retaining the existing edit action.

## Focused region comparison evidence

The side-by-side comparison focuses on the complete sheet because the changed controls, row rhythm, promotion, expected total, and bottom action all fit in one readable crop. A separate detail crop was not needed: the 30px steppers and their icons/numerals are legible at the full 390px viewport.

## Required fidelity surfaces

- Fonts and typography: existing project font stack, weights, line heights, price hierarchy, and compact secondary copy are preserved. Quantity numerals use the same compact UI weight and remain readable.
- Spacing and layout rhythm: row separators, 13px vertical rhythm, right-aligned pricing, promotion spacing, and footer proportions match the source. The stepper is 30px high and aligns with the existing edit control without horizontal overflow.
- Colors and visual tokens: pure-white surfaces, deep green text, pale-green controls, warm-gold prices, and the existing promotion card tokens are unchanged. The removed destructive red treatment is intentionally replaced by the requested green minus control.
- Image quality and asset fidelity: this component contains no raster imagery. Minus/plus/pencil/close/sparkle visuals use the project's existing Lucide icon dependency; no handmade SVG, text glyph, emoji, CSS-art asset, or placeholder was introduced.
- Copy and content: “修改”、项目 names、promotion copy、“预计合计” and “最终以门店账单为准” are unchanged. Screen-reader labels explicitly say “增加/减少 + 项目名”.

## Interaction evidence

- Plus on “腰臀调理” changes quantity `1 → 2`, row total `¥69 → ¥138`, selected count `4 → 5`, and expected total `¥207 → ¥276`.
- Minus changes quantity `2 → 1` and restores count/amount to `4 / ¥207`.
- Minus at one removes the row through the same state-cleanup path as the former delete action.
- Different body parts remain separate rows; increasing one part does not duplicate another part.
- Promotion remains based on distinct eligible body parts, so repeating the same part cannot manufacture another promotion qualification.
- Browser console errors checked: 0.

## Comparison history

1. First rendered iteration: visual control placement passed, but the editable sheet retained the old server snapshot total after quantity increased. Classified P1 because the row price and expected total disagreed.
2. Fix: added an explicit payable-display rule—editable selections use the live local preview; read-only confirmed selections use the frozen server total.
3. Second rendered iteration: quantity, row total, selected count, promotion, overall expected total, and decrement restoration all agree. No actionable P0/P1/P2 visual or interaction findings remain.

## Findings

No actionable P0/P1/P2 findings remain.

## Implementation Checklist

- [x] Compact plus/minus control replaces the service-row delete button.
- [x] Edit entry remains available.
- [x] Quantity, item price, count, promotion, and expected total update together.
- [x] 390 × 844 layout has no horizontal overflow or clipped primary action.
- [x] Full frontend tests, TypeScript check, production build, primary interaction, and console check pass.

## Follow-up Polish

No P3 follow-up is required for this scoped change.

final result: passed
