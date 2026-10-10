# Design QA — 技师服务后快速交接

## 对照对象

- 设计方向：`C:\Users\gaoji\.codex\generated_images\01a06c30-8114-7211-ac49-95477f19d482\exec-1ad9ffcf-1277-406f-9b72-03b19071b75f.png`
- 实际实现：`.playwright-cli\page-2026-09-21T10-27-34-149Z.png`
- 验证视口：390 × 844，本地 HTTP 页面，生产只读登录，本地网络桩提供一条已完成服务及 v7 字典；未发起生产写入。

## 检查结果

- 信息层级符合目标：服务上下文、交接预览、三个核心问题、选填补充、确认与固定底部操作。
- 主路径无需输入文字；点选沟通方式、部位、下次动作与本次调整后，预览即时生成。
- 部位动作采用二段式选择，避免把“哪里”和“下次怎么做”混成平铺标签。
- 年龄段为互不重叠的七档；性别仅男、女，未选择即不记录。
- 基本信息和本人补充默认折叠，核心任务保持短而清晰。
- 选中态、触控尺寸、对比度、焦点轮廓与底部安全区满足移动端使用要求。
- 服务单抽屉只显示中文业务名称与服务位，不再暴露 `#position-*` 等内部标识。
- 浏览器控制台无新增错误；两条警告来自现有 Ant Design 运行时，不影响本流程。

final result: passed

## CUSTOMER-SERVICE-ACCOUNT-SHEET-02-FIDELITY — 2026-10-10

This review supersedes the previous acceptance of the standing mascot pose.

- Source: `C:/Users/gaoji/AppData/Local/Temp/codex-clipboard-598b7498-da49-4d31-9f8e-dc09dde81cb9.png`, 853x1844, normalized to 390x844.
- Implementation: `diy-web/output/playwright/customer-service-account-sheet-fidelity/390x844-my-sheet.png`; CSS viewport 390x844, density 1.
- Combined comparison: `diy-web/output/playwright/customer-service-account-sheet-fidelity/reference-vs-implementation.png` (780x844). Both show My with the sheet open; the synthetic non-member identity is intentionally not falsified to match the reference membership.
- Short-screen evidence: `375x568-my-sheet.png` in the same directory. The QR stays fully visible; secondary content scrolls inside the sheet and the close control remains fixed.

### Findings and comparison history

- P1 fixed: the old standing 3D mascot did not match the peeking 2D child. Two independent transparent generated assets now supply the leaf-hat head, edge-resting hands and mint marks, and the matching basket avatar. Existing brand assets remain untouched.
- P2 fixed: the former separate copy button did not reproduce the unified pale search strip. The strip now has the reference radius, background and restrained divider.
- P2 fixed after the first capture: the taller sheet started at y150. Reducing the gaps around identity, steps and secondary text moves the revised sheet to approximately y182; the actual QR ink region is approximately 190px wide at y405, with its original quiet zone preserved.
- Typography: scoped system sans-serif stack, 24px title, 18px identity/action and 14px secondary hierarchy. No new font dependency or license introduced. Platform glyph rendering remains slightly different from the raster reference (P3).
- Layout: white rounded sheet, left peeking artwork, 60px circular avatar, compact steps and full-width search strip checked in the combined capture. No viewport overflow.
- Colors: white content, dark-green hierarchy, pale mint auxiliary surfaces and muted text match the reference direction; no gradients or replacement UI raster.
- Assets: both PNGs visually inspected; alpha preserved, no full-sheet rasterization. QR SHA256 remains `2316315edb11d0f701f2326697a3123c85ed38b5b037e27d7f1b4e59fad6f299` and offline decoding is unchanged.
- Content: all account text, instructions, voluntary/login notices and clipboard success/failure wording remain unchanged. WeCom and business flows unchanged.

### Verification

- Four real local component runs: 375/390 x 844/568, home/My entry, QR visibility and long-press semantics, copy success/denial, close/Escape and unchanged WeCom entry; no console errors.
- `npm test -- --run`: 250 passed, 1 existing skipped. Vite teardown emitted dependency-scan diagnostics but tests exited 0 with no failures.
- `npm run build`: passed. `git diff --check`: passed.
- No production write, report access or real WeChat follow action. Field recognition remains a post-release check.

final result: passed

---

# CUSTOMER-SERVICE-ACCOUNT-SHEET-02 — 2026-10-10

## 对照对象与归一化

- Source visual truth: `C:/Users/gaoji/.codex/generated_images/01a0c1a4-f8e1-73c0-9c87-42051db50bd5/exec-fd9ff895-1036-4619-a5f1-75eb6dd5d4d2.png`，853×1844px。
- Implementation: `diy-web/output/playwright/customer-service-account-sheet-02/390x844-my-sheet.png`，390×844px，CSS viewport390×844，deviceScaleFactor=1。
- Same-input comparison: `diy-web/output/playwright/customer-service-account-sheet-02/reference-vs-implementation.png`。左侧源图等比缩至390×约843px、右侧实现390×844px；不比较像素密度、源图虚构二维码图案或背景顾客业务数据。两者均为已登录“我的”上打开服务号弹层；实际背景身份为隔离合成顾客，源图背景为示意年度会员。
- 375×844、390×844及375/390×568短屏另外验证。实际IAB在390×844打开并检查服务号弹层；一次脚本截图及结果均为真实本地H5组件，无生产写入。

## Findings / 五项对照

- 无遗留可执行P0/P1/P2问题。白色大圆角底部弹层、标题/服务号身份/两步/二维码/操作说明/备用搜索/自愿提示顺序与选定方案一致。
- 字体：沿用现有项目字体及回退，标题23px、名称19px、主操作17px、说明14px、低级备用11px；与归一化源图接近，375px无标题截断。源图含示意字体，不引入新字体。
- 布局：左右24px、大圆角26px，390px实际顶部约163px（源图约182px）；约19px差来自保留原字体/真实二维码静区及滚动适配，属于可接受的生产约束，不改变主区域层级。短屏主二维码初始完整，辅助内容内部滚动，关闭始终可见；短屏隐藏外伸装饰IP，避免挡住核心操作。
- 色彩：纯白主体、现有深绿标题、浅绿步骤及轻辅助底色，原品牌色系无新渐变或图案。
- 图片：真实258×258服务号原JPEG，SHA256 `2316315EDB11D0F701F2326697A3123C85ED38B5B037E27D7F1B4E59FAD6F299` 与输入逐字节一致，离线解码为用户提供原载荷；显示210/218px等比，不裁切/重绘/生成示意码。顶部及身份IP使用已有hxy-mascot.webp，姿态/渲染与示意图不同是用户要求复用现有品牌素材的明确约束，未以CSS/SVG绘制替代。
- 文案：标题、名称、两步、长按说明、底部菜单与项目/本人报告说明均匹配指定内容。URL框及复制链接CTA删除；复制名称只作为弱化备用，成功/失败明确，不承诺已关注或自动免登录授权。

## Focused evidence / 交互与历史

- 图文/二维码/步骤及关闭在全图390px已经清晰可读；追加 `375x568-home-sheet.png` 核对短屏完整二维码和关闭，`375x568-copy-failure.png` 核对滚动至底部及失败兜底，不需进一步模糊缩小的局部截图。
- 初次短屏截图包含既有选单临时toast，不能作为稳定弹层对照；脚本改为等其隐藏后捕获，同视口重拍短屏证据，核心区域不再遮挡。未修改已有业务toast。
- 已测首页及我的入口、复制名称成功/浏览器拒绝失败、关闭/ESC、原企微弹窗仍可打开；原码可读、img user-select:auto且无contextmenu处理；4组页面无控制台异常或横向溢出。未测试真实微信关注动作，不自动添加。
- 关闭与复制按钮语义/焦点围栏复用原组件；无新增动画，系统长按未禁。原报告授权及有效登录未修改。

## Implementation checklist

- [x] 原码逐字节复用及离线载荷确认。
- [x] 底部弹层、已有IP、两步、大二维码与弱化搜索。
- [x] 375/390及短屏、两个入口、关闭、复制双状态、企微不变。
- [x] 同输入源图/实现对照；构建与顾客端测试。

## Follow-up polish / 现场边界

- 无P3必须追加改动。真实微信长按识别服务号、关注及底部菜单到店流程由总控/用户在发布后核验，不把本地验证当现场完成。

final result: passed
