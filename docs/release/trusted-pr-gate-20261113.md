# Trusted PR Gate 正式作业修复

## 已核验故障

PR #479 的 head `433f9be8021e30a281b297dcc941c80aed7f2df3` 六项必需检查均 success，但正常 REST/GraphQL 合并仍返回 `Required status check "Trusted PR Gate" is expected.`。主干保护和 app ID 正确，最新测试合并提交没有其他检查或同名 commit status。

原工作流以 `checks.create` 手工补写总结果。该结果被 GitHub 自动归入 `Quality gates` 的 pull_request 检查组（117156432360），而不是产生测试证据的可信工作流；此前成功的 #477/#478 分别归入 pull_request_target 检查组。API 不支持指定 check suite，重新执行发布步骤也没有改变归属。不能把 API 中 success 等同合并保护已接受；GitHub 内部判定细节无法从公开 API 完整证明。

## 修复与边界

- CI 增加正式命名为 `Trusted PR Gate` 的 Actions 作业，先要求静态检查、后台/顾客构建及后端测试全部成功。
- 再用只读 Actions API 核验同仓库、同分支、精确 head、固定路径、pull_request_target 事件的最新可信工作流；该工作流仍由主干定义，原权限隔离和测试保留。
- scope、四类测试和 Publish trusted result 六个真实作业必须全部 success。缺失、跳过、取消、超时或 head 变化均失败，不接受任意手工 check run。
- 删除可信工作流手工生成 check run 和 checks:write 权限；总结果由原生 Actions 作业登记。切换 PR 使用主干旧版可信工作流，其真实作业仍被完整核验。
- 不更改分支保护、必需检查名称、App 限制、生产部署入口、数据库或旧业务资料。不伪造成功、不直推主干。

行为验证覆盖来源过滤、精确 SHA、最新运行/尝试、失败与缺失、超时及核验期间 head 变化。生产结果另以实际部署记录为准。
