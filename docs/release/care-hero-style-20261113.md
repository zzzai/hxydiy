# Care hero style release — 2026-11-13

## 2026-11-13 肩颈与腰臀主图风格统一已上线

- [PR #484](https://github.com/zzzai/hxydiy/pull/484) 已合并发布；运行 SHA `f2876481ec3727feda65ceebe56916a62c702ab9`，current=`github-f2876481ec37-43368772505`。精确 [CI 43368314990](https://github.com/zzzai/hxydiy/actions/runs/43368314990) 与唯一 [Deploy 43368772505](https://github.com/zzzai/hxydiy/actions/runs/43368772505) 通过。
- 两张主图改为同一套白底留白、淡绿水彩、圆润荷叶帽IP，保留自然肩颈动作与腰臀完整床面支撑。使用独立 `main-v3` 文件；旧主图和详情v2保留。此次图片提交没有价格、券规则或数据变更。
- 顾客端生产构建、62项既有测试通过；实际React与隔离合成API在375/390px通过菜单/详情图片及无溢出核验，完整图片与截图已目视检查。真机现场体验不冒充自动化验收。
- 真实备份与隔离恢复通过；发布前备份恢复基准与发布后71张表的行数、内容摘要完全一致，其中70张为业务表。无迁移、回填，验证业务写入0。
- 828项MANIFEST、188个运行Python文件、14项公网资源验证通过；两张v3主图与保留详情的公网SHA一致，旧图仍保留。
- 本次发布以已合并主干`7c5ab06ae4e7c1eff828c6fb92e85996cb90cb26`为基线，包含此前独立合并的[券运营PR #483](https://github.com/zzzai/hxydiy/pull/483)；不是回退到旧后台，也不把该批业务改动记作图片提交。后端运行文件与该受检主干一致，数据库结构版本保持。
- [设计与截图](../design/care-hero-style-20261113.md)、[脱敏证据](evidence/care-hero-style-20261113.json)。本次事实补录不再次部署。

## Rollback and verification boundary

Restore only the two hero mappings to the retained `-main-v2.webp` files through a forward release. Preserve the merged coupon workbench, historical assets, prices and all database records. Do not restore an old full database to roll back artwork. No rollback was performed.

Production verification only read static resources, health and aggregate table hashes. No real coupon generation/claim/redemption, SMS, member edits or other production business writes were performed. The actual backup was restored into a separately named rehearsal database; only that temporary verification database was removed after validation.
