# 原打印短码绑定纠正

状态：开发及验证；未应用生产。总控唯一执行生产应用。

## 目标与授权

原20260923八张纸码编号1、2、3、5、6、7、8、9不变；QR ID 3、4、5、6、7、8、9、10分别调整到room ID 4、3、2、1、8、7、6、5。当前Rooms ID/code/name/customer_label/地图/状态不变；QR public_id/short_code_hash/source/status不变，短码和v3签名不变，不搬历史room_id。本次明确修正之前仅更名操作中的“不改绑定”边界，非自动扩大普通二维码生命周期权限。

用户已在总控窗口明确这些关联记录都是测试，允许只收尾仍开放记录、保留历史不删除。但精确预检显示当前8个房位available、活动引用0；15条draft/submitted均已过期、无关联订单；3条post_service_present历史记录均无active_room_id/active_session_id。唯一pending服务行属于cancelled选单且占用released。故本工具不清理、不取消这些历史，也不造服务结束或支付。以后若发现真正活动业务，工具拒绝，先按另行固定清单和既有域流程关闭，不能凭本次测试确认覆盖后来新增记录。

历史状态记录：room1/5号沙发、room4/1号沙发、room6/8号沙发各一条无活动引用的post_service_present。最后更新时间分别为2026-09-05 09:23:35 UTC、09-14 03:36:23 UTC、09-10 10:53:09 UTC。不能将其称为实际未释放的3个服务位。

## 执行顺序

1. 合并及部署包含入口锁后复核的精确提交；若还未部署，必须先停止接单入口并等待全部在途请求完成，不能只复制工具后在线换绑。
2. 总控核验官方完整备份、SHA256和隔离恢复演练。将真实dump只读挂载/复制到工具可读位置，不使用非空证明文件冒充备份。
3. 在含本次scripts/app的执行环境默认预览；生产使用当前容器环境，不复制/打印密钥。首次完整mapping必须与原8张码匹配，保留preview_hash和所有保护哈希。
4. 携带预览哈希及备份SHA显式apply。事务对相关表取EXCLUSIVE锁，5秒锁超时、30秒语句超时；其他查询仍可读，写入/行锁请求等待。任何漂移/活动业务拒绝并回滚。需要短维护窗口；不自动重试或清理。
5. 再预览应changed=0、阻断计数0；protected QR、Rooms和history哈希与应用前一致。原8短码逐一307到同纸面编号，v3签名复核正常；旧seat入口403后重扫，不放宽权限。总控记录真实生产证据，现场贴码扫码由人验收。

```sh
PYTHONPATH=/app python -m scripts.rebind_printed_sofas
PYTHONPATH=/app python -m scripts.rebind_printed_sofas --apply \
  --expected-hash <preview_hash> \
  --backup-reference <actual_dump_path> --backup-sha256 <verified_dump_sha256>
PYTHONPATH=/app python -m scripts.rebind_printed_sofas
```

脚本会导入同版本 `scripts.relabel_sofas` 验证当前坐标/标签；须完整提供这两个scripts模块，不单独复制文件后忘记依赖。没有迁移/删库/重印/状态轮换。受控交换临时借用一个同店空闲、无有效码、无活动引用/派钟的现有空间容器，FK和唯一索引不关闭；停车绑定从不提交。写入仅8条room_id和单条审计，调用方异常必须回滚。

## 回退边界

事务失败自动整体回滚，无停车状态提交。成功后若核验异常，停止入口，保留证据并交总控决定受控逆向换绑；不得直接恢复整库覆盖后续订单，不提供自动逆向/自动全库恢复。纸码不含room_id，短码与v3仅依赖未变身份。v2长码携带旧位置，不属于本次原纸面短码兼容保证。

## 验证

`hxy-server/tests/test_rebind_printed_sofas.py` 使用真实SQLite外键/有效room唯一索引；可通过 `QR_BINDING_TEST_DATABASE_URL` 在独立数据库 `qr_binding_test` 重跑，每例独立随机schema，禁止生产库。测试覆盖默认只读、事务回滚、完整交换、同码签名保留、重复幂等、活动业务与新增历史漂移拒绝、停车不可用、入口初次校验后发生换绑的403。测试与精确提交证据由交接报告提供，本文不冒充生产/现场验收。
