# 管理后台目录恢复发布验收

日期：2026-10-24。状态：已合并、已生产核验；人工现场验收另行记录。

- `ADMIN-CATALOG-RECOVERY-20261024` 已上线：[PR #380](https://github.com/zzzai/hxydiy/pull/380)，候选 `c6128ce43b13db1be84c22dfded30813c3efe2f3`，合并/生产 `8362674795a09da45c3e4402efd6e84b1993fa7f`；精确 [CI 40081262322](https://github.com/zzzai/hxydiy/actions/runs/40081262322) 与唯一 [Deploy 40081627303](https://github.com/zzzai/hxydiy/actions/runs/40081627303) 成功，备份/恢复演练/部署/验证 job 成功。实际 current=`github-8362674795a0-40081627303`。
- 服务项目编辑按真实接口限制校验，图片上传携带门店；已发布可选内容先创建草稿再编辑，重复/并发复用一份草稿，旧版不可变，保存后校验发布并刷新返回状态。页面内容、操作记录、分群和规则使用业务表单或中文摘要，未知历史字段保留；停用规则只是配置，未启用执行、发券或消息。
- 生产核验 510 项 MANIFEST、169 个安装 Python 文件、3 个运行源文件与 10 个公网入口/资源哈希一致，health=`ok/production`；本次备份文件 checksum 通过。迁移集合及内容与前一版一致，没有数据库结构、凭据、余额、会员或历史订单变更。
- 验收使用隔离合成 PostgreSQL（51 项真实 HTTP）、27 项后端目录合同、30 项前端定向检查、TypeScript/构建和真实组件浏览器保存/发布回读。生产复核不调用业务写接口、不查询顾客数据，业务写入 0；人工现场验收仍由人完成。详见 `operations/admin-catalog-recovery-release-20261024.md`。本次事实文档收尾不再次部署。

## 精确范围

本批业务提交共 37 个文件，实施于 hxy 独立工作区。范围为项目编辑、图片、错误恢复、目录草稿与发布、已验收 JSON 展示表单化及合同/测试/文档。未纳入预览夹具、合成登录页、依赖链接、会员同步、支付退款、任务自动同步或其他未验收功能。主干原有相对上版生产的差异仅为发布事实文档。

## 验证与回退依据

- 发布前主干 CI 成功；使用官方部署工作流下载精确 SHA 的管理端和顾客端制品，经保护发布器备份、独立库恢复演练和校验后切换。
- 生产备份：`/root/hxy-diy-20260811/backups/pre-github-8362674795a0-40081627303-20261024T094001Z.dump`，大小 786992 字节，SHA256 `f700c876e2f7ab38cc2cc240987a3a9f2a30845af0e6236b253eabe00b60d452`。备份内容不进入 Git；本记录仅存校验信息。
- 当前 MANIFEST SHA256：`6faf8502e1220711c6ad4437c005e1a0220ed4b5f1aec1651714cdab6d436154`。上版 release `github-7684ff3bab9c-39979231372` 保留，没有清理旧版本或数据。
- 原有合同验证和价格/权限边界保留；新增接口仅创建编辑草稿，未迁移或回填旧目录。
- 健康检查和资源一致性不代表已替员工在生产提交服务项目，也不代表企微真机验收。生产没有执行测试保存/发布业务请求。

## 证据

总控本机 `output/admin-catalog-release-20261024/ci-result.json`、`deployment-result.json`、`production-verification-8362674795a0-40081627303.json`、`commit-scope.json`；发布前隔离证据见 `../product/admin-catalog-integration-acceptance-v3-20261024.md`。服务器副本位于 `/root/hxy-diy-private-operations/admin-catalog-release-20261024/`。

本文件为发布后事实记录，合并文档不再次触发生产发布。
