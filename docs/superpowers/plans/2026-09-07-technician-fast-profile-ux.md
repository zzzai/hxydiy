# 技师端一分钟顾客快记实施计划

> 执行方式：本窗口按任务逐项实现与验证，不使用子代理。

**目标：** 服务结束后的默认页面让技师在一分钟内完成高频记录；身体相关情况使用结构化、非诊疗化的顾客自述条目；本人历史能区分长期确认与仅本次观察。

**架构：** 保留 v1/v2/v3 记录只读兼容，增加 `schema_version=4` 与 `taxonomy_version=service_reference_v3`。身体条目只保存在追加式服务记录中，不进入 `customer_profile_current`、自动分群、定价或营销。

**约束：** 不记录诊断、药品名、收入、资产、联系方式或人格评价；原话最多 100 字；身体条目最多 3 条；技师仅可写本人已完成服务。

## Task 1：v4 身体状况合同

**文件：** `hxy-server/app/api/admin_v2.py`、`hxy-server/app/api/technician.py`、`hxy-server/app/domain/wellness_profile.py`、`hxy-server/tests/test_technician_profile_v3_contract.py`、`docs/contracts/service-reference-v1.md`、`docs/TEAM-MEMORY.md`。

- [ ] 先在 `test_technician_profile_v3_contract.py` 新增失败用例：`body_service_notes=[{"area":"knee","context":"old_injury","reconfirm_next_visit":true}]` 可保存，未知编码与超过三条返回 422。
- [ ] 运行 `python -m pytest hxy-server/tests/test_technician_profile_v3_contract.py -k v4 -q`，确认当前模型拒绝 v4。
- [ ] 在 Pydantic 中定义 `ServiceReferenceV4BodyNote`：部位仅限肩颈、背部、腰臀、手臂、膝周、腿部、腹部、足部、皮肤；情况仅限顾客提及旧伤、术后恢复、近期不适、长期不适、皮肤敏感、下次确认；每条默认下次确认。
- [ ] 将 v4 taxonomy、请求校验和存储加入既有服务记录路径；画像投影函数明确忽略 v4 身体条目。
- [ ] 运行 `python -m pytest hxy-server/tests/test_technician_profile_v3_contract.py hxy-server/tests/test_customer_profile_projection.py -q`，通过后提交 `feat(profile): add safe body service notes contract`。

## Task 2：分层快记页面

**文件：** `admin-react/src/technician/serviceReference.ts`、`admin-react/src/technician/TechnicianProfileSheet.tsx`、`admin-react/src/technician/technician-mobile.css`、`admin-react/tests/technician-profile-v3.test.ts`。

- [ ] 先新增失败结构测试，断言存在“一分钟快记”“记录身体状况”“顾客自述，非诊断”和 `buildServiceReferenceV4Payload`。
- [ ] 运行 `npm test -- --runInBand tests/technician-profile-v3.test.ts`，确认当前页面没有独立入口。
- [ ] 首屏仅保留：重点/谨慎部位、力度/温度、服务反馈、下次建议。新增“记录身体状况”底部抽屉，按“部位 + 顾客自述情况 + 下次确认”点选，已选项可删除。
- [ ] 年龄、体型、工作生活、沟通消费进入“补充画像”，默认折叠。保存摘要必须区分“顾客自述身体状况”和“技师本次观察”。
- [ ] 运行 `npm test -- --runInBand tests/technician-profile-v3.test.ts`、`npx tsc --noEmit`、`npm run build`，通过后提交 `feat(technician): streamline service profile quick note`。

## Task 3：历史安全摘要与交付

**文件：** `admin-react/src/technician/TechnicianServiceHistoryPage.tsx`、`admin-react/src/technician/technicianMobile.ts`、`admin-react/tests/technician-profile-v3.test.ts`、`docs/workstreams/technician.md`。

- [ ] 先新增失败测试：历史页有“顾客已确认”和“仅本次观察”的明确状态。
- [ ] 历史卡保留脱敏顾客、服务位、项目、时长和安全服务偏好；身体条目只显示“需服务前再确认”，不展示疾病、用药或原话。
- [ ] 执行 `npm test && npx tsc --noEmit && npm run build && python -m pytest hxy-server/tests/test_technician_profile_v3_contract.py hxy-server/tests/test_customer_profile_projection.py -q && git diff --check`。
- [ ] 推送 PR；合并后再进行备份、恢复演练、Manifest、迁移、健康检查与 390x844 真机验收。仅发布成功后更新 `docs/CURRENT-STATE.md` 和 `docs/WORK-STATUS.md`。

## 自检

- 已覆盖高频快记、身体自述、低频折叠、确认摘要、历史状态和投影排除。
- 不建设数据仓库、AI 分群、自动营销、跨店搜索或诊疗能力。
