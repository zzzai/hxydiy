# 企微技师隔离联调：资源恢复门禁

2026-10-17。仅本批隔离任务，不是生产发布记录。用户恢复服务器后明确要求先核资源及遗留进程、限制资源，再恢复后台/技师分工联调；保留已有修改，不动生产库、不提交、不合并、不部署。

## 总控只读核验（19:20 北京时间）

- hxy SSH 恢复；4 核、总内存 3917 MiB、无 swap；MemAvailable 2676 MiB，限额操作后 2623 MiB；load 0.02/0.05/0.08，memory PSI full avg10 为 0。
- 根盘 40G，使用 91%，余 3.6G。本批不执行清理、拉取新镜像或无界输出。
- 未发现 cwd 属于本批 worktree 的 node/python/uvicorn 遗留进程；旧 PG/test 均 exited，故无须杀进程或删除文件。
- 旧 PG 仅内存盘；test 仅挂载本批 hxy-server 源码；未见生产数据挂载。本轮未读取容器凭据、生产库或真实顾客数据。
- 工作区 HEAD 仍为 77ce71fd0133471a067b9fdeefa59c3c93eaad6a，原有未提交/未跟踪修改仍在。
- 公开首页返回 HTTP 200，仅作为连通性证据；前次失联根因仍未确认，当前和上一启动内核查询未返回 OOM 记录，不据此排除资源问题。

## 已落地的资源上限

- hxy-wecom-pg-20261017：memory 268435456，memory-swap 268435456，NanoCpus 500000000，pids 64，restart=no；设置后仍退出。
- hxy-wecom-test-20261017：memory 536870912，memory-swap 536870912，NanoCpus 500000000，pids 128，restart=no；设置后仍退出。
- 两容器限额已 docker inspect 读回核实。未修改任何生产容器。
- 单次 transient true 探针成功：MemoryHigh=768M、MemoryMax=1G、MemorySwapMax=0、CPUQuota=100%、TasksMax=128、RuntimeMaxSec=600；不是前端构建通过。

## 执行顺序与停止条件

1. 后台先按 v3 的 28 文件逐项备份、比对和协调同步，不能盲目对部分已改的服务器工作区应用干净基线补丁；技师和总控文件保留。
2. 旧 PG tmpfs 未限定 size，保留退出状态。后台仅新建 hxy-wecom-pg-bounded-20261017，复用已有 PG 镜像、internal 网络和合成配置；tmpfs 128MiB、memory 256MiB、swap=memory、CPU 0.5、pids 64、restart=no，读回确认后运行。不使用真实备份或 Secret。
3. 重任务启动前 MemAvailable 至少 2GiB、根盘余量至少 2GiB；脚本每 5 秒采样：MemAvailable 低于 1GiB 或根盘低于 2GiB 立即停止本批确切资源；memory full avg10 至少 1% 连续 3 次停止。测试总超时 600 秒。
4. 后台先串行完成 PG 迁移、并发和原数据保护，再交合成 fixture API 给技师浏览器闭环。未验证的 PG 项不能跳过并宣称通过。
5. 构建与后端测试不得并行；构建期间停止本批两个测试容器。前端只能使用上述 transient 硬上限，NODE_OPTIONS old-space 640MiB；运行时核实际属性，超限/OOM/超时保留失败证据并停止，不自动扩额或重试。
6. 不按宽泛 node/python 名称终止进程；只操作已核定本批容器或 transient unit。不得因测试失败重启生产服务或数据库。

状态：资源预检和旧测试容器限额已核实；后台获准先恢复受控隔离验证，技师可同步独占文件，但等待后端 PG 阶段完成后才运行浏览器联调。业务整体仍未终验，真实企微及真实报告来源仍未验。

总控保留本机 BACKEND-HANDOFF-RECEIPT-v1.md 的 v3 哈希核验记录；该接收记录不代替本文件后的服务器测试结果。
