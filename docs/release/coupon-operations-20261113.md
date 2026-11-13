# 券运营规则修正与工作台（2026-11-13）

## 交付状态

- 业务 PR：[#483](https://github.com/zzzai/hxydiy/pull/483)，合并 `7c5ab06ae4e7c1eff828c6fb92e85996cb90cb26`。
- 精确 main CI：[43367608411](https://github.com/zzzai/hxydiy/actions/runs/43367608411)，success。
- 该提交随后包含在 main `f2876481ec3727feda65ceebe56916a62c702ab9` 中；生产 current=`github-f2876481ec37-43368772505`，[Deploy 43368772505](https://github.com/zzzai/hxydiy/actions/runs/43368772505) success。该部署由另一发布窗口触发，本窗口只读核验。
- 本次无数据库迁移、无旧券/历史数据回填、无真实批量发券/短信/支付/消息。

## 已交付

- P0：percent_off 语义和校验、零预算、规则写权限、分页、核销时间窗、有效过期状态、模板创建/更新审计。
- P1：券运营概览、规则详情/编辑、海报记录及原入口预览/下载、券台账、核销记录、筛选后全量脱敏 CSV 导出。
- 店长移动端继续只做发券、核销、本店记录；管理端规则写入仅品牌管理员。

## 验证

- `hxy-server` targeted：58 passed，12 skipped。
- 新增 `test_coupon_admin_contract.py`：7 passed。
- 完整后端（本机缺少 schemathesis 的单独测试文件被 ignored）：1352 passed，30 skipped，103 subtests passed。
- 隔离 PostgreSQL 并发锁测试：1 passed。
- `admin-react`：318 passed；`npm run build` 通过。
- 生产只读：`/admin/` 200、健康接口 200、品牌管理员 `GET /admin/v2/coupons/overview` 200；没有业务写入。
- 已安装 admin 入口 `/admin/assets/index-646a8EXH.js`，CouponsPage chunk `/admin/assets/CouponsPage-DqGrShVi.js`。

## 边界与回退

- 不新增数据库结构；应用回退到前一已验证 release 即可；旧券、旧领取关系和历史审计不动。
- P2（会员同步只读状态、经营口径整合、学习/AI 总部管理补全）不在本 PR 范围，未声称完成。
- 真实微信/企微摄像头、本人核对、门店现场核销仍待人工验收。
