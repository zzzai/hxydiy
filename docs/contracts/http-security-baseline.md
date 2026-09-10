# HTTP 浏览器安全基线

更新日期：2026-09-10

## 适用范围

DIY 的顾客端、技师端、管理端、公开分享页及 `/api/v1/` 统一由服务端附加本基线；它不替代接口的身份、门店、状态、幂等与审计校验。

## 响应规则

- 所有响应包含 `X-Content-Type-Options: nosniff`、`Referrer-Policy: strict-origin-when-cross-origin`、`X-Frame-Options: SAMEORIGIN` 和受限 CSP。
- CSP 仅允许本站脚本、同源连接、本站/`data:`/HTTPS 图片；禁止对象嵌入、外部框架嵌入与跨站表单提交。样式保留内联样式兼容，不以此放宽脚本来源。
- `/api/v1/` 响应为 `Cache-Control: no-store`，不得由浏览器或中间缓存保存令牌、匿名会话凭证或顾客数据。
- production 额外使用一年期 `Strict-Transport-Security`；本地和测试不发送，避免误导 HTTP 开发环境。

## XSS 与 CSRF 边界

- 顾客 H5 使用 React 默认转义，禁止新增 `dangerouslySetInnerHTML` 或未经白名单清洗的 HTML 注入；公开分享页必须 HTML 转义元数据，且不使用内联脚本。
- 顾客登录令牌只能由 `Authorization` 请求头提交；匿名与可信设备 Cookie 必须为 `HttpOnly + Secure(production) + SameSite=Lax`。未配置跨域放行时，跨站脚本不得读取 API 响应。
- 安全头是纵深防御；每个写接口仍必须验证授权、资源归属、状态机与幂等性。新增第三方嵌入、外部脚本、跨域 API 或 Cookie 鉴权写接口前，必须先扩展本合同并补 CSRF/CSP 回归。
