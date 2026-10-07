# SEAT-LABEL-20261007 production configuration delivery

## Applied configuration

Applied on hxy on 2026-10-07 (Asia/Shanghai). Configuration-only transaction; no application restart, full release, QR regeneration or file/image replacement.

| Fixed grid, top to bottom | Stable ID / code | Old label | New label |
|---|---|---|---|
| Left 1 | 1 / sofa-01 | 1 | 5 |
| Left 2 | 2 / sofa-02 | 2 | 3 |
| Left 3 | 3 / sofa-03 | 3 | 2 |
| Left 4 | 4 / sofa-04 | 5 | 1 |
| Right 1 | 5 / sofa-05 | 6 | 9 |
| Right 2 | 6 / sofa-06 | 7 | 8 |
| Right 3 | 7 / sofa-07 | 8 | 7 |
| Right 4 | 8 / sofa-08 | 9 | 6 |

Only `rooms.name` and `rooms.customer_label` updated, with a system audit entry. Coordinates, QR records, stable identifiers, service state and order ownership untouched. Historical item/pricing/transition snapshots not rewritten; live Room-name joins show the new label.

## Verified preparation and execution

- Exact reviewed tool HEAD: `f498c29fbc4eace8f5d5612708744f9fdf975937`, PR #216. Tool SHA256: `3ce54107a5760af4381dbfe1e608888d6378a18f106c4d40b64a9070fc5edcfa`.
- Tool staged at `/tmp/hxy-seat-label.pKNF5G/hxy-server/scripts/relabel_sofas.py`, copied to the existing API container `/tmp/relabel_sofas.py` and run with its existing environment. No secrets printed.
- Before backup: `/root/hxy-diy-20260811/backups/daily/daily-20261007T063512Z-7b3d0bb6dae34f58b95a3695.dump`; 644344 bytes; SHA256 `ac2525ab3b03d6a2f5c9418fe09a6914faee602b9dbd69d7a7377ba8ead8ed22`. Official backup and isolated restoration passed; container backup copy `/tmp/seat-label-20261007-before.dump` had the same SHA.
- Local 9 tests and server-isolated 9 tests passed; production readonly preview expected exactly 8 changes. Root reviewed tool diff, protection audit and the compact evidence `C:\Users\gaoji\AppData\Local\Temp\SEAT-LABEL-20261007-evidence.json`.
- Production `--apply --backup-reference /tmp/seat-label-20261007-before.dump`: changed=8. Subsequent readonly preview: changed=0.
- Before/after `/tmp/seat-label-protection-20261007.py` output matched all 8 protected SHA256 fingerprints, including static position/QR identities and mapping. QR IDs 3 through 10 still map to room IDs 1 through 8. No plaintext tokens or customer data recorded.
- Public service-position-map returns target labels at unchanged coordinates. Actual logged-in customer browser refresh shows sofa-01 as 5号沙发; opening the seat dialog shows left top-to-bottom 5/3/2/1 and right 9/8/7/6. No seat-change button or order action was clicked; browser stays on the verified map.
- Runtime release remains `github-add74e7f5a6f-37573479507`. PR #216 merge is script-managed; installation of this one-shot tool does not require an application release. Printed QR images remain unchanged; physical placement/scan acceptance not performed.

## Recovery

If configuration verification later fails, the same guarded tool supports `--restore --apply` using the verified backup reference. Restore only labels; do not restore the entire production database or rotate QR tokens. Never run store bootstrap/preview setup to rename seats.
