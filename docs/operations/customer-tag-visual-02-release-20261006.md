# CUSTOMER-TAG-VISUAL-02 交付证据

- 使用 systematic-debugging 复现真实列表路径：App使用完整摘要，11px两行截断挤长流程；catalog span选择器覆盖简介/选购颜色。frontend-design用于收敛现有品牌的字级、行距与职责层级，未重建布局。
- 仅改 App列表摘要调用、domain列表专用文案/标签映射、列表CSS及menu-tags测试。经典草本泡为“泡脚配肩颈按摩，兼顾脚部清洁”，招牌草本泡为“从肩背到双脚，搭配草本热敷”；保留全部映射特色，按真实内容显示有用次层，不堆重复/通用规则。详情完整流程及原摘要函数未改变；图片、价格、分钟、菜单数据、品牌顶部、评价、报告、后端未改。
- PR #207 HEAD `88ff3c6e52425caab575d6e26d91c0d383ca183f`；主干 `3541f050a8b6eeebd4df7b5ec858f22c93c400dd`。CI `37488849113`、官方部署 `37489296171` 成功；单次精确HEAD门禁与现有官方发布流程，没有重复部署。发布前可用容量5139369984字节。
- `node --experimental-strip-types --test tests/menu-tags.test.ts tests/domain.test.ts`：51 passed；`npm run build`：退出0。375/390实际旧生产前端与新本地构建使用同公开目录及真实图片，隔离合成会话API；前后截图及JSON在顾客worktree `output/playwright/customer-tag-visual-02/`。加号触控打开详情、经典完整流程保留、返回列表、分类、无溢出及选购计算颜色通过。
- 部署后再次使用实际生产前端375/390验证，不是仅检查代码存在：简介12px，特色 `rgb(23, 104, 86)`/浅绿底，选购 `rgb(154, 114, 32)`/透明底；同触控/详情/分类断言通过，截图为 `375-production.png`、`390-production.png`。会话/选单API仍转发隔离合成后端，公开目录与图片真实，不写生产选单或真实身份。
- current `/root/hxy-diy-20260811/releases/github-3541f050a8b6-37489296171`，MANIFEST通过，DIY/TCM健康200；匿名报告/授权401、来源公网404、既有只读配置有效。公网页面匹配当前 `index-B1_DiPUe.js`。桌面报告为共享Git `hxy-release-reports/customer-tag-visual-02-release-20261006.json`；服务器证据为 `/root/hxy-diy-20260811/operations/tcm-production-verification-20261006-3541f050a8b6.json`。
- 未操作真实顾客授权、登录或报告；微信/门店现场未验收。旧补测试提交与生成文件保护、未纳入本批。此记录仅文档，不再次部署。
