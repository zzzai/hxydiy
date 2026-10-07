# SEAT-LABEL-20261007：固定格子显示编号

仅一次性门店1配置调整，无迁移、应用重部署或新后台入口。准备完成不代表生产已应用。

| 固定格子（上到下） | ID / code | 初始名称 → 目标名称 |
|---|---|---|
| 左1 | 1 / sofa-01 | 1号沙发 → 5号沙发 |
| 左2 | 2 / sofa-02 | 2号沙发 → 3号沙发 |
| 左3 | 3 / sofa-03 | 3号沙发 → 2号沙发 |
| 左4 | 4 / sofa-04 | 5号沙发 → 1号沙发 |
| 右1 | 5 / sofa-05 | 6号沙发 → 9号沙发 |
| 右2 | 6 / sofa-06 | 7号沙发 → 8号沙发 |
| 右3 | 7 / sofa-07 | 8号沙发 → 7号沙发 |
| 右4 | 8 / sofa-08 | 9号沙发 → 6号沙发 |

左侧map_x=0.08，右侧0.70；每侧map_y=0.14/0.34/0.54/0.74。前端按map_x分侧、map_y升序展示，不改坐标或排序。二维码图片、短码、签名token、底层ID/code及所有订单/占用关联保持不变。历史items/pricing/transition快照不改；按当前Room.name关联显示的页面会显示新名称，不代表历史归属变化。

总控先完成正式备份、校验和隔离恢复演练；将本脚本及已验证的非空备份或私有备份证明复制到API容器可读的临时路径。`--backup-reference` 仅检查文件非空且非符号链接，不代替备份校验及恢复演练。使用当前容器的应用环境，不复制或打印环境变量。

```sh
python /tmp/relabel_sofas.py
python /tmp/relabel_sofas.py --apply --backup-reference /tmp/verified-backup-reference
python /tmp/relabel_sofas.py
# Restore only the eight previous labels if verification fails:
python /tmp/relabel_sofas.py --restore --apply --backup-reference /tmp/verified-backup-reference
```

默认预览为PostgreSQL只读事务；apply锁定本店配置、整批验证后仅更新name/customer_label，追加system审计，同事务提交。ID/code/布局或名称漂移、店内重复目标标签均拒绝；仅接受完整初始或完整目标状态，重复执行/恢复零改动。PostgreSQL锁等待5秒、语句30秒超时。当前存在活动占用不阻止更名，也不改服务状态。

应用后核对8格新名称，比较受保护静态位置/QR指纹，验证旧码同ID/code/token及在途引用不变；刷新顾客页面。真实二维码位置验收交给人。不要运行bootstrap_diy_store或setup_preview作为生产更新，它们是初始化工具，含旧初始名称且修改范围更广。
