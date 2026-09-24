# Auxiliary service menu v1

Store 1 exposes exactly six standalone `辅` projects in this order. Amounts are cents; no group price is inferred for new projects.

| Code | Name | Store | Member | Description |
| --- | --- | ---: | ---: | --- |
| `hxy-head-30` | 头疗 | 7900 | 4900 | Existing 30-minute service |
| `hxy-foot-refine-1` | 足部精修 | 6900 | 3900 | Existing service; append-only store price change |
| `hxy-oil-back-30` | 精油开背 | 9900 | 6900 | 背部精油按摩30分钟 |
| `hxy-caier-30` | 采耳 | 8900 | 5900 | Existing 30-minute service |
| `hxy-jubu-30` | 局部推拿 | 7900 | 4900 | 肩颈、腰背、腿部、腹部、足部任选其一 |
| `hxy-cupping-scraping-1` | 拔罐/刮痧 | 5900 | 2900 | Required free single choice: 拔罐护理 or 刮痧护理 |

Existing `hxy-baguan-1` and `hxy-guasha-1` remain published with their IDs, prices, detail routes, historical snapshots and published `linked_project_id` references. Only their `independently_visible` flag becomes false, excluding them from the standalone customer list. The default is true for all projects. The admin list/edit and public detail route still include hidden standalone items; a published parent's linked choices still resolve. Hiding does not cancel or reprice an existing selection, service line or order.

The combined project's published option catalog requires exactly one free care method. Its selected choice is preserved in selection and service-line snapshots. Neither choice adds a separate charge.

Deploy the visibility migration before running `python -m scripts.reconcile_aux_menu --store-id 1 --apply`. The script defaults to dry-run and checks expected codes/prices. Apply only after a database backup and restore rehearsal. Successful re-execution must be a no-op. The schema migration supports downgrade; operational menu rollback must use new audited catalog and price versions rather than rewrite frozen snapshots.

The historical `腰臀` choice in already-published parent catalogs is not silently rewritten by this change. It requires a separate versioned parent-catalog update; the customer UI wording must be synchronized by its owning window. Browser, phone and store acceptance remain human tasks.
