# 门店日常作业真实接口验收 v2

2026-10-24。状态：服务器独立工作区已实现，隔离真实HTTP/数据库与浏览器已验收；本机快照构建通过。未提交、推送、开PR、合并、部署；没有生产数据库操作。保留已有修改与v1模拟预览。

## 入口与基线

- 完整预览：`http://127.0.0.1:4216/tests/daily-operations-live.html?page=today`。页内可切换今日工作台、到店选单、服务待办、顾客反馈、员工账号；“切换测试角色”提供店长、另一门店、只读员工、总部四个合成角色。
- 员工账号仅总部可访问。店长不因预览获得总部权限。测试登录使用专用合成账号，预览不加载正式账号或浏览器凭据。
- hxy工作区 `/root/hxy-diy-development/mobile-workbench-closeout-20261023`；分支 `codex/admin-daily-operations-preview-20261024`，HEAD/origin/main均为 `26fff1c8243dcf845c2f507a3e82ce659fa7aa12`。
- 本机只运行服务器哈希核验源码快照，未在本机修改业务代码。v2前端快照SHA256：`20952eac49aecaaea6794b00e9f3025b8d2636f49adedad039743e73d3b96d83`。

## 隔离与资源

- PostgreSQL使用既有隔离容器中新建的 `daily_ops_20261024` 合成库，未连接正式PostgreSQL。保留上一批catalog隔离环境。
- 新API容器 `hxy-daily-preview-api`，512MiB、0.5CPU、120PID、一个worker；数据库既有限额384MiB/0.35CPU；Docker internal网络，无API公网映射。外部消息、企微调用与调度关闭。
- 本机通过仅回环SSH隧道连测试API，Vite4216仅回环监听；预览Node上限512MiB，完整构建上限768MiB。无依赖升级。
- 预览为了给用户查看而保留；刷新后仍读合成库，不保证断开SSH或关机后地址继续有效。

## 根因与已验证结果

|范围|结果|
|---|---|
|真实API|`network-http-d0d7ede3.json` 42项断言通过；69条封装请求加独立并发请求，直接网络HTTP连接运行中的FastAPI与PostgreSQL，不以ASGI替代|
|无座确认|并发确认返回同一确认时间，只生成一个执行项目与一次审计；无座可确认；同座重复配位返回同一占用；UI确认后原单出现在已确认列表|
|门店与角色|跨店选单/配位/待办/评价拒绝，只读员工与技师不能执行店长动作；店长不能访问总部员工账号；切换门店后列表不带上家数据|
|待办并发|受控PG行锁下两个resolve请求仅一个200，另一个409；完成审计一次，原说明不被覆盖；重复认领无额外审计|
|待办回读|UI知悉后仍留未处理，显示处理人和时间；填写说明保存后进处理记录，重新打开原文一致|
|评价一次保存|状态选择和说明输入不发保存；数据库仍为open/空说明/零审计；真实API中断时错误可见且草稿保留，恢复后一次保存；回读状态和原文一致，保存审计一次|
|评价并发与分页|两类评价相同内容重试不重复审计，保存时间保持；强制并发两请求成功但仅一审计。UI真实分页20条，第二页与第一页不同，筛选回到第一页|
|员工筛选|姓名、登录名（大小写不敏感）、角色与门店AND组合只返回匹配账号；%按字面处理；重置恢复4条合成账号；刷新有新的真实GET请求|
|当前服务投影|工作台读取当前服务位，真实已确认执行项目能出现；跳“查看服务位”进入实际看板。无座未配位选单仍在到店选单查看|
|漏单误报|当前执行项目不再因缺旧订单误报；2个正常选单被排除、1个故意缺执行项目的合成选单仍被发现；网络核验零写入。异单修订不能冒充有效履约|
|单元/合同|原有员工与移动工作台16项、增量保存筛选4项、新执行项目核对1项、旧核对兼容1项通过；ASGI/SQLite证据单列，不冒充PG并发|
|前端|服务器TypeScript no-emit通过；同哈希本机快照完整生产构建通过（14.86秒），既有大包体积警告保留；浏览器13项操作证据通过|
|布局|1365px桌面截图，390px今日/选单文档宽度均390；表格区域横滚，未造成整页横向溢出；结束时恢复视口设置|

## 证据与失败保留

私有服务端证据：`/root/hxy-diy-private-operations/admin-daily-integration-20261024/state/`。

- 最终网络：`network-http-d0d7ede3.json`。
- 最终新合同：`backend-new-contracts-final.log`；原有16项通过见 `backend-contracts.log`。
- 补充核对：`reconciliation-after.json`、`reconciliation-regression.log`；新关联回归单测本轮命令输出1 passed。
- 浏览器写回：`browser-writes-verified.json`、`feedback-browser-unsaved.json`、`feedback-browser-saved.json`、`browser-acceptance.json`。
- 编译：`typecheck-live-v2.log`（退出0）。本机输出目录 `output/admin-daily-integration-20261024/` 保留 `build-live-v2.log`、截图与同名验收资料。
- `network-http-152be9b7.json` 保留初次失败：测试误把幂等重复配位的200当409，纠正测试预期后通过，没有修改配位业务。
- 新合同初次2项失败为SQLite时间戳时区显示差异，修正测试比较后4项通过；PG保存时间严格相等已独立通过。
- 评价中断测试仅短暂停止本批API，已恢复；截图 `feedback-failure.png` 记录预期错误，不是未解决故障。

## 文件归属与未覆盖范围

- 后台API：`hxy-server/app/api/admin.py`、`admin_v2.py`；合同测试 `test_admin_daily_operations.py`；OpenAPI与生成类型同步。
- 前端：今日/选单/待办/反馈/员工页面，dailyOperations与样式；独立预览fixture不替换正式入口。
- 文档：PRD v2、三份接口合同、TEAM-MEMORY候选条目；生产CURRENT-STATE不改。
- 价格、会员权益、真实员工/顾客、钱包、旧订单不修改。无数据库迁移、无自动关闭历史误报、无支付退款和外部消息。
- 仍需后续：超时待办派生、历史异常人工核实、1000条扫描/200条待办上限及分页、其他管理模块巡检。不是所有后台功能均已完成。
- 本次没有CI/生产/真机验收声明；真机仍由人执行，用户预览确认后再进入下一交付阶段。
