# 顾客项目列表主图铺满

## 范围

`CUSTOMER-MAIN-IMAGE-FIT-01`：用户确认对比预览并授权修改、合并、生产发布。

- 仅项目列表主图：内边距由3px改0，完整缩放改为等比铺满；共用 `hxy-spa-60.webp` 的舒压SPA和精油开背采用靠右居中取景。
- 原图片文件、78×86外框、圆角、菜单、价格、标签、其他布局及项目详情头图不变；原图自带插画留白仍保留。不改数据库、服务位或会员及报告规则。
- 顾客PR #230，精确HEAD `dce5e25e37d98a62af5fff375fbfdd9ec2b0cf04`，基线 `c3c5a7a46b24262b7522d7198da402632b2faf8c`。

## 本地证据

- 顾客端唯一实现/验收窗口：构建通过，现有列表样式专项4项通过，diff检查通过。
- 375/390px实际组件共28张列表图检查通过：图片成功加载、最终计算样式为cover/0px，SPA为100% 50%，无横向溢出；实际组件图集核对无明显主体误裁。
- 使用公网公开项目目录的只读快照，在本地H5与合成服务位中渲染，未生产下单或写数据库。证据为顾客工作区 `diy-web/output/playwright/customer-main-image-fit-01/result.json`、`375/390-menu.png`及`375/390-all-images.png`。
- 总控核对精确diff、验收报告和截图，复用有效验证，不重复实现或运行本地验收。

## 生产交付

- 已合并主干 `8f7438ceba911446c82e90842cbe526c88a30595`；精确主干CI `37946311535`成功。正式部署 `37946921274`成功，版本资格检查及受保护备份/演练/部署/核验均通过；只发起一次发布。
- 服务器current为 `github-8f7438ceba91-37946921274`，`MANIFEST.sha256`通过。公网HTML引用安装资源，JS `/assets/index-yQFXVL4V.js` SHA256 `f0652b6c18be0e85bfce92249968287e07cfc378fe4f0efc6a8e112f1c044198`、CSS `/assets/index-mmBT0ioM.css` SHA256 `91b656007614cb30f7682474f77df66414bc579006b2004e6c4b99b1c29d1b39`均与安装一致。
- 公网实际CSS确认主图cover/零内边距及SPA right center取景规则；健康200、匿名报告及授权401、TCM内部读取公网404。未读取顾客真实健康报告，未创建测试占用或选单，无生产业务数据应用。
- 总控证据 `output/main-image-fit-20261009/{deployment,production-verification}.json`及`installed-public.css`。本条记录已核验事实，文档合并不再重复部署。

## 现场边界

真实微信及门店现场未验收；本次不新增测试占用或选单。
