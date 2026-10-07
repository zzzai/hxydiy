# CUSTOMER-MY-STABILITY-03 production delivery

## Scope and decision

- Fix repeated loading in My page; hide customer dynamic membership code and historical orders/visits and derived savings/counts temporarily.
- Choose reversible presentation hiding: no reliable test-record marker exists. User identified historical orders as tests, but this release does not prove every database row is a test or delete any row.
- Preserve identity/price refresh, member rights/type/expiry, coupons for nonmembers, current submitted selections/services, report entry and menu feedback. No API/schema/database/consent/menu changes.

## Exact release

- PR #212: `88a36834233589248070270f855f6845ee9933f7`.
- Merged main: `8dbfdcdd4b3418d1c5caa508dc75c90715cce5a5`.
- Main CI: `37570016321`, success.
- Official deployment: `37570280991`, success; release report `C:\Users\gaoji\AppData\Local\Temp\CUSTOMER-MY-STABILITY-RELEASE-20261007.json`, terminal=true.
- hxy current: `/root/hxy-diy-20260811/releases/github-8dbfdcdd4b34-37570280991`.
- MANIFEST passed, DIY/TCM health 200, anonymous DIY reports/consent 401, public source reader 404. Unchanged source reader SHA: `695bbd707add456fdbae90df1122e79069bceb7a6cb5e639bece5aa507713008`.
- Server evidence: `/root/hxy-diy-20260811/operations/tcm-production-verification-20261006-8dbfdcdd4b34.json`; unchanged reader verification reused, no new health data queried.

## Root cause and verification

- Parent identity refresh runs every five seconds and on foreground events. Profile effect depended on the entire newly created auth object, reloading historical data and flashing the loader.
- Stable token/member dependencies and request-context guards discard old responses, including stale 401 after new login or membership change.
- Customer worktree: `C:\Users\gaoji\.codex\worktrees\customer-review-five\customer`.
- Evidence directory: `diy-web/output/playwright/customer-my-stability-03/` (`before-result.json`, `after-result.json`, `late-result.json`, before/after 375/390 screenshots).
- 375 member and 390 nonmember: eleven seconds plus foreground refresh. Before: orders/mine five requests each, loading entries three. After: orders/mine zero, loading zero, no remount; identity refresh remains. Nonmember coupons load once. Report return/login and menu feedback/price preserved.
- Three stale-response scenarios passed; build and 39 relevant tests passed. Local browser uses isolated synthetic APIs, not production records or field acceptance.
- Production logged-in Codex browser refreshed and opened My: member type/expiry and report entry present; dynamic code, historical tabs/list and historical summary absent. No logout, OTP, number change, consent submission or production order write performed during this check.
- WeChat and store acceptance not performed. No repeated valid local checks or additional deployment for these documentation changes.
