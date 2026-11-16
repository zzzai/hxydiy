# Member finance incremental acceptance

The 2026-11-16 user instruction is to skip retirement facts that cannot be queried and to synchronize only currently queryable, verified facts. Missing cards, zero balance and unlinked refunds do not authorize retirement. The retirement draft is isolated and is not part of this release.

Reuse the existing append-only financial importer and the existing four tables. On repeat synchronization the full observed packet may contain existing bills. Freeze the exact read-only preview counts, bind them to the input/manifest/runtime SHA, and require those exact additions after the transaction. Do not use the full packet length as the expected insert count. A new source revision conflict stops this controlled flow for review.

Customer verification includes the complete observed owned-bill subset, all existing visible history, per-row source/store/person isolation and the newest appended balance. Existing legitimate records outside the current input remain visible; they are not a cross-person leak. Unverified refund/payment evidence keeps savings unknown. No old card, user, balance, wallet, order, price or financial row is updated.

A new batch still requires new normal-UI source observations, complete pages, exact source hashes, a current read-only protection baseline, a real backup, isolated restore/application/projection/replay verification, then one transaction and a zero-write duplicate preview. The host runner accepts only date-scoped member-history directories directly under /root/hxy-diy-private-operations. No old manifest is replayed.

Validation and production outcome are recorded separately with the batch receipts. This document alone is not evidence of a production import or app deployment.
