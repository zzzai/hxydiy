# Care hero artwork consistency — 2026-11-13

## Problem and scope

The two care-kit heroes used a dense yellow room and taller character proportions, while the existing menu illustrations use open white space, sage watercolor accents and a round lotus-hat mascot. Only the waist and neck main images and their mappings are replaced. Detail v2 artwork, historical asset files, prices, coupon rules, APIs and database data remain unchanged.

Initial validation base: `a5afe13c259e795e95b6bca73573cb8c1a65abee`. Rebased onto merged main `7c5ab06ae4e7c1eff828c6fb92e85996cb90cb26` before submission. The intervening coupon administration PR changes no `diy-web` files; the tested customer source and image evidence remain unchanged. Full CI runs on the final PR head.

## Visual treatment

The existing `hxy-spa-90.webp` and `hxy-spa-60.webp` establish the style. Both new illustrations share white margins, pale sage washes, soft ink outlines, an ivory/green outfit and a moderate curved lotus-hat stalk. The mascot has rounder proportions. Sparse lotus, bamboo, a towel and a small kit support the service scene without a full interior backdrop.

The neck scene keeps connected arms and hands on the seated customer's shoulders. The waist scene keeps the entire prone customer supported by a complete mattress, including the legs and feet. These are brand scene illustrations, not clinical instruction diagrams.

Generated with built-in `image_gen`; [exact prompts](evidence/care-hero-style-20261113/generation-prompts.json). PNG originals are retained in the task output outside Git. WebP encoding changes only the file format (quality 0.88), preserving the 1254 × 1254 composition.

| Asset | Bytes |
| --- | ---: |
| `hxy-neck-kit-10-main-v3.webp` | 136068 |
| `hxy-waist-kit-10-main-v3.webp` | 134702 |

## Reviewed screenshots

- [Menu at 390px](evidence/care-hero-style-20261113/menu-390.png)
- [Waist hero at 390px](evidence/care-hero-style-20261113/waist-hero-390.png)
- [Neck hero at 390px](evidence/care-hero-style-20261113/neck-hero-390.png)

Actual React production build with the existing isolated synthetic API was checked at 375 and 390px. Both menu rows and detail headers load the v3 heroes; detail sections continue to load v2. No horizontal overflow, page errors or external requests occurred. Only synthetic preview sessions/events were created; no production writes. Full-size images and the encoded screenshots were visually inspected for anatomy, linework, white space, palette and crop.

## Validation

- `npm run build`: passed in the isolated server worktree.
- Existing domain, project asset and detail visual tests: 62 passed, 0 failed. Node 20 uses esbuild-transpiled test files; the detail suite's temporary file was placed alongside its source to preserve relative URL semantics, then removed.
- `output/care-hero-style/`: build log, test logs, asset metadata, browser report, original generation inputs and mobile screenshots.
- This record establishes pre-release validation only. Production delivery must be recorded separately after the normal CI and backup/restore gates.

## Rollback

Restore only the two `projectImage` mappings to their retained `-main-v2.webp` files through the normal release process. No database rollback, historical data edits or price changes are needed.
