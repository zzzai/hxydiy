# TECHNICIAN-BASIC-TAGS-VISIBLE-20261015

状态：已发布生产；自动化与只读生产验证通过，真实微信和门店现场待验。

## 范围

- 技师服务交接把既有年龄段、性别从“补充基本信息”折叠项移到主流程第一步直接展示。
- 年龄档仍为`25–29`、`30–34`、`35–39`、`40–44`、`45–49`、`50–59`、`60以上`；性别仍只有男、女。
- 沟通方式、重点部位及下次动作、本次调整顺延为第二至第四步。字段、API、保存和确认语义、跨技师及管理端可见范围、历史记录、会员、价格、权限和数据库均未改变。

## 版本与门禁

- 业务PR：[#271](https://github.com/zzzai/hxydiy/pull/271)，候选`5dd23262f79c75e8554321ea001dde1a53a03368`，合并/发布主干`1fa97d179c1f15e8d842d108d26dab13ca023f54`。
- 本地证据：管理端前端测试`222 passed`、生产构建和`git diff --check`通过。
- 精确main CI [38717299576](https://github.com/zzzai/hxydiy/actions/runs/38717299576)成功，管理端与顾客端双制品齐全。正式部署仅派发一次：[38725804357](https://github.com/zzzai/hxydiy/actions/runs/38725804357)；资格校验及“Backup, rehearse, deploy and verify”均成功。
- 发布前current为`github-0b88c66e5763-38713160429`，两把发布锁均空闲，可用`5067152 KiB`。本批业务差异仅一个前端组件及其测试，使用CI双制品及服务器既有镜像/构建缓存；原3 GiB门槛只是部署脚本的最低保留空间，不作为完整峰值预算，也未降低或绕过。没有清理旧release、数据库或备份。

## 生产终验

- 实际current为`/root/hxy-diy-20260811/releases/github-1fa97d179c1f-38725804357`；完整`MANIFEST.sha256` 457项通过，清单SHA256为`148403565448815ab143cc124d43fc1a44797926146923b7434a667b71c37998`。终验时可用`5017508 KiB`。
- 精确CI管理端制品`admin-dist-1fa97d179c1f15e8d842d108d26dab13ca023f54`的主JS `index-rRTajQ-E.js`和CSS `index-C74SkvdW.css`，分别为`332de58a8bdd4337d48bed1d9f2979a103e9ce4eca10cd5f0ff8136f3678fce4`、`760896e3d648683caf9a25f2dfd283edff324df3956a28b48bfef075f3e587d7`；安装文件与公网资源逐项同哈希，公网HTML与安装`index.html`同哈希且Content-Type为`text/html`，JS为`text/javascript`。
- 生产主JS包含“顾客基本信息”“年龄段”“性别”，不含旧“补充基本信息（选填）”标题。后端年龄和性别选项未改；安装`technician.py`的Git blob为`c0fc44a64581e9fb9fc9e6cf36f65d589d358ecb`，与精确主干raw blob相同，安装和运行容器SHA256均为`a444a95494bef8e00b8e3be79f4df33efc3da43cde15aa3a45622d4fe25cf17f`。
- `/api/v1/health`返回`ok/production`；技师登录页和今日页匿名HTML均为200。只把精确health JSON当作健康证据；任意未知`/api`路径可能由SPA回退为HTML 200，不作为API暴露或健康证据。

## 未验范围

- 没有使用真实技师账号或读取真实顾客数据，没有执行开始、结束、保存记录等生产写操作。
- 真实微信浏览器、登录后完成服务时的交互、弱网和门店现场仍待验；本地测试、CI、部署成功、health和匿名HTML均不能替代现场验收。
