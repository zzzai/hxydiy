# Waist and neck care project visual refresh — 2026-11-13

## Scope and source

- Base: `origin/main` `7f8ab2001a0abdad104d95bca162cfda5ef5a4cc`.
- Replaces only the two kit project image mappings and adds dedicated detail visual sections. Previous image files remain available.
- Source: user-provided `荷悦臻养产品手册_v4.pptx`, SHA256 `379b2b72135a29b59e2190e1460df9441596af1cf84accf5a01cc18963733ffe`.
- Slides 3 and 9 establish the powder, liquid and oil kit; slide 20 supplies the three 20-minute service stages; slide 29 limits customer-facing language to relaxation/care and individual comfort.
- The handbook is internal source material, not automatically approved advertising copy. Sales scripts, medical claims, new price offers and qualification marks are not copied into the page.

## Visual approach

The existing menu uses hand-painted watercolor art. Both projects retain the same lotus-leaf-hat mascot, rounded proportions, moderate curved stalk, warm ivory, sage and light oak. Waist and shoulder service positions distinguish the main thumbnails. The long details illustrate the closing warm-compress/head-relaxation stage and the kit supplies; they are scene illustrations, not clinical operation diagrams.

Four active versioned files in `diy-web/public/assets/projects/`:

- `hxy-waist-kit-10-main-v2.webp` (1254 x 1254)
- `hxy-neck-kit-10-main-v2.webp` (1254 x 1254)
- `hxy-waist-kit-10-detail-v2.webp` (1024 x 1536)
- `hxy-neck-kit-10-detail-v2.webp` (1024 x 1536)

Generated using built-in image_gen with current brand assets and source kit photographs as references. PNG originals are retained outside Git. WebP encoding preserves dimensions and composition; encoded assets are 186–264 KB each. The source PPT and original assets are not modified.

## Validation and delivery

- `npm run build`: passed on the isolated server worktree.
- Existing project asset, detail visual and half-price contract suites: 11 passed, 0 failed (Node 20 uses temporary esbuild-transpiled tests; temporary files removed).
- Actual React production build with isolated synthetic HTTP API: both projects render their dedicated main and detail images at 375 and 390 pixel viewports; no horizontal overflow, browser exceptions or external requests.
- Preview starts synthetic selection sessions/events only. No production API/business data writes; no price, coupon, schema or membership changes.
- Evidence: `output/care-project-images/{assets.json,browser-report.json,build-v2.log,tests.log}` and mobile screenshots. Output files are not committed.
- Design preview: `/review/` on the isolated server port 18448; actual menu: `/?store=1&view=menu`.
- Delivery status: published through PR #479 on 2026-11-13. Exact production SHA, verification and rollback are recorded in `../release/care-project-images-20261113.md`. Earlier preview evidence is retained; no data rollback is needed.

## Anatomy correction after visual review

The first generated main images were rejected: the waist image obscured full mattress support and the neck image had ambiguous wrist/forearm continuity. Main v2 reconstructs a fully supported horizontal prone customer and separately connected caregiving arms/hands. V1 source PNGs remain in the local design output and server originals folder. Only v2 is mapped in the application and review page; detail v1 was subsequently superseded as recorded below.

## Detail image correction

User review identified the same unsupported/distorted covered lower-body shape in both detail v1 images. Both detail v2 images reconstruct the full supported prone silhouette, with two visible feet, a complete mattress and a sage throw confined to the mattress top. The waist compress remains at the lumbar area; the neck compress remains at the upper shoulders. Main v2 images and all business content remain unchanged. Old detail files are retained; all active app and review mappings use detail v2. Validation is recorded in `build-detail-v2.log`, `tests-detail-v2.log` and `browser-report.json`. These checks validate rendering/assets; visual anatomy was separately inspected in the full images and mobile screenshots.

## Menu simplification and release approval

On 2026-11-13 the user approved publishing the corrected images and requested removal of the redundant notice at the top of the claimed-voucher menu. The `half-price-menu-note` banner and its unused styles are removed. Per-project voucher prices, exclusions and store redemption guidance remain intact; this is a presentation change, not a coupon contract change.

The Unslop skill by Damir Sokolovsky ([source](https://github.com/heydamir/unslop), CC BY 4.0) was reviewed as a lightweight UI audit reference. Its useful principles here are reducing repeated copy, keeping interface chrome quiet, and preserving existing brand/layout. It was not installed globally. Desktop-specific dimensions and subjective typography restrictions are not adopted as mobile Chinese UI rules. The reference cannot replace data/permission tests or anatomical image review.

Release-candidate validation: production frontend build and 11 focused asset/detail/pricing tests passed. The actual React menu against real HTTP and isolated PostgreSQL passed 9 end-to-end cases: no top coupon banner; five exact voucher prices; nine excluded rows; 375/390 px non-overlap; ordinary anonymous browsing; login/claim binding; other-browser claimed state; one-time manager redemption; and ordinary prices after consumption. No external requests, real SMS or production business writes. Evidence: `output/care-project-images/{build-release.log,tests-release.log,coupon-menu-report.json}`. Prior image rendering evidence remains valid because this follow-up only removes the banner and its CSS.

## Reviewed screenshots

Screenshots use synthetic data, never real customer records. Main/detail screens were inspected at 375 and 390 px; the following 390 px evidence is retained for PR review.

- [Claimed-voucher menu without the top coupon banner](evidence/care-project-images-20261113/menu-foot-390.png)
- [Waist main](evidence/care-project-images-20261113/waist-hero-390.png) and [waist detail](evidence/care-project-images-20261113/waist-detail-390.png)
- [Neck main](evidence/care-project-images-20261113/neck-hero-390.png) and [neck detail](evidence/care-project-images-20261113/neck-detail-390.png)

Initial full CI correctly rejected stale `domain.test.ts` expectations that still mapped the two kits to borrowed SPA/head images. Those exact assertions are updated to the approved dedicated assets; assertions still reject legacy backend photographs. The first PR also lacked the required design-evidence heading; screenshots and the review section have now been supplied. No check is bypassed.
