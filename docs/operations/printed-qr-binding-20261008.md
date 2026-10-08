# 原打印短码绑定纠正

状态：已合并、生产发布及换绑核验通过；实体/微信扫码未验收。总控唯一执行生产应用。

## 2026-10-08 生产事实（Asia/Shanghai）

- #219 HEAD `948cb2480a13cda746cdc6c661d260e2ab06fe41` 合并为 `3b5629a36c6810a238ea76782ce722caebaeafa6`；主干CI `37668858811` 成功。此前可选AI审查写回404，失败job重试后审查完成为skipped，云AI关闭；未绕过门禁。
- 正式部署 `37689786435` 成功，current `/root/hxy-diy-20260811/releases/github-3b5629a36c68-37689786435`；MANIFEST校验及公网health通过。容器入口SHA `a43f1fe4480e038e896612c9613abe1f60151e4f0f318f922805bc9a2afc20fb`，工具SHA `e3077eb2d75109b65049655347653d5e77159a0c51fe382e5ffb06ab43df806e`，依赖SHA `3ce54107a5760af4381dbfe1e608888d6378a18f106c4d40b64a9070fc5edcfa`。
- 发布后发现09:31新增占用647、room1/5号沙发，draft无订单；总控停止应用，用户本轮单独确认“是测试”。只在精确ID、门店、未提交/未服务/无派钟与无变更请求检查通过后调用既有释放领域方法，选单过期、审计留存；未删除或伪造服务完成。其他过期/已释放历史不变。初次检查使用不存在的派钟字段失败，事务回滚、未写；改为真实room关联检查后收尾成功。
- 应用前新官方备份 `/root/hxy-diy-20260811/backups/daily/daily-20261008T013446Z-2ed19445f85148f5bd3d318d.dump`，648042字节，SHA `77f530cf819138c621d8243f2ec2ae931998815a143a175b030192e5d5b84caf`，隔离恢复成功；真实dump复制至容器 `/tmp/qr-printed-preapply-20261008.dump` 后再次核验SHA。
- 收尾后新preview hash `f3d65cd166605e51194ab57f6a91c8c2f9b6cc8d945f732fef4b6410d372397f`，阻断全部0；显式apply更新8条，后预览changed=0、阻断0。应用前后QR身份hash `6e896f170b594b167733a51d2dc01f2529e2984ebbdf37ab1029e594815b9262`、Rooms hash `894d1675d1b6d69cb93e2a56630d098ff633b47ce3b7f162486e755c8a648660`、历史hash `4c8b3583e0982b07333f74ce5ab4adbf578c84387a01f5693428d5c2a868e979` 一致。历史hash基线在已授权测试收尾之后建立，不能声称收尾前后历史状态不变。
- 用户指定原目录8张PNG与参考导出逐张SHA相同，解码原短链后全部HTTP307到正确seat；纸面标签与公网地图一致，8个v3签名有效、8个旧seat入口403；仅只读签名校验，没有创建生产选单。短码访问自身的访问时间/审计正常更新不属于业务选单。

| 原图文件 | 纸面与扫码编号 | 当前room ID / code |
|---|---|---|
| sofa-01 | 1 | 4 / sofa-04 |
| sofa-02 | 2 | 3 / sofa-03 |
| sofa-03 | 3 | 2 / sofa-02 |
| sofa-04 | 5 | 1 / sofa-01 |
| sofa-05 | 6 | 8 / sofa-08 |
| sofa-06 | 7 | 7 / sofa-07 |
| sofa-07 | 8 | 6 / sofa-06 |
| sofa-08 | 9 | 5 / sofa-05 |

本地精简证据位于总控隔离工作区 `output/qr-printed-binding-20261008/` 的 `deployment.json`、`test-closure.json`、`binding-application.json`、`printed-verification.json`，不含短码/签名令牌。用户原图片未编辑或重生成。现场按纸面编号贴对应沙发，重新扫码，不使用微信旧页面历史链接；实物可识别、真实设备菜单打开仍须门店核对。菜单、价格、会员、评价与报告均未改；文档记录不触发额外生产发布。

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
