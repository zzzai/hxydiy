# Customer H5 review disposition — 2026-10-01

Baseline: origin/main `9736a79285eea60dff12611872be54e3a52bcc66`.

1. SPA gift versus standalone foot bath — business decision required. The published 60-minute and 90-minute SPA descriptions say they include a complimentary herbal soak, while the catalog separately sells `hxy-qiqing-30`. Descriptive text alone does not define fulfillment or discount eligibility. No automatic removal, repricing, or bundle rule was added. Product/operations must define whether both can be selected and how the included soak is fulfilled before pricing changes.
2. Structured herbal formula missing from selection summary — fixed. The sheet and submitted-order summary now resolve selected preference choice IDs against the published catalog while preserving legacy preference labels; linked-project choices are not shown as formula preferences.
3. Featured SPA price identity — fixed in presentation only. The featured `hxy-spa-90` card shows the project's own name and exact displayed price without a “starting at” suffix. The 60-minute SPA remains a separate catalog item; no prices changed.
4. Detail hero height — reduced on mobile with `contain` to keep the existing IP/image intact and bring options closer. Desktop styling remains unchanged.
5. Tiny explanatory text — selection-sheet payment note and success note increased to 13px with readable contrast.

Validation: `npm run build` passed; after the build generated expected assets, the complete sequential web suite passed (240 passed, 1 skipped). The first test run before building failed one asset-presence test because this fresh worktree had no `dist`; it passed after build. This review does not establish production deployment or store/WeChat acceptance.
