# TCM-REPORT-UI-02 交付证据

- 根因：ProfilePage 左上角直接调用 onClose，关闭整个个人中心；报告内部另有返回入口，语义不一致。现有报告子页返回明确关闭 reportsOpen，个人中心保留；直接报告入口重复打开同步恢复子页。
- 单一顾客窗口修改 MyReports、ProfilePage、报告专属 styles.css 与相关回归脚本，使用 frontend-design 精修标题、留白、空状态、列表和原始数值；没有新增依赖、医学结论或数据图表猜测，保留真实报告标题与独立撤回入口。
- PR #203 精确HEAD `e7573629575e4240d85f4ba62740711eb292ad2e`；合并主干 `83da0f3db25f0cfe659a75c3a1b47633a5fc5826`。主干CI `37470492560`、正式部署 `37471148998` 成功。
- 本地构建与20项测试退出0；375/390授权、空、列表、详情、不可用状态验证采用合成账号和真实报告API，未模拟报告授权返回。结果在顾客worktree `output/playwright/tcm-report-ui-02/result.json`；原报告 unavailable.backToMy=false 是未覆盖项，补测结果 `failure-back/result.json` 两尺寸均true。补测试提交 `5d71ca9743f119942611a1b869df89044093a2e3` 在PR合并后推送，不属于本次生产；实际业务源码未因补测试而变化。
- 生产 current `/root/hxy-diy-20260811/releases/github-83da0f3db25f-37471148998`；MANIFEST通过，DIY/TCM健康200、公网源读取404、匿名DIY报告及授权401，独立读取密钥和固定内网地址配置仍有效。复用不变源模块证据，不重复安装查询服务或读取他人报告。服务器证据 `/root/hxy-diy-20260811/operations/tcm-production-verification-20261006-83da0f3db25f.json`，桌面发布报告在共享Git `hxy-release-reports/tcm-ui-release-20261006.json`。
- 用户本人内置浏览器：有效登录与独立授权保留，报告显示真实空列表；新版空状态可见，点击“返回我的”后个人中心报告入口及退出登录仍可见，无重复短信验证。未撤回授权、换号、写订单或替用户同意。
- 本次已闭环 UI 与返回问题；本人真实报告详情尚未读取，因为当前手机号列表为空。不用门店分析HTML替代个人报告，不把桌面浏览器或合成回归当作微信真机、现场验收。
