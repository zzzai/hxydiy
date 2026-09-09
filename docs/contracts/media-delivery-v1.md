# 管理端媒体交付 v1

## 稳定引用

`POST /api/v1/admin/media` 与媒体列表的 `url` 统一返回稳定的受控内容地址：

```text
/api/v1/admin/media/{media_id}/content
```

项目、商品和加项表单只能保存该稳定地址，不得保存对象存储或 CDN 的临时签名 URL。

## 读取与权限

`GET /api/v1/admin/media/{media_id}/content` 继续校验当前员工的门店范围和软删除状态。对象存储支持签名 URL 时，服务端在该请求中生成并以跳转返回短期 URL；本地存储继续代理内容。该实现不扩大媒体读取权限。

本期不处理既有目录中已经保存的外部或过期 URL，不增加迁移、裁剪、压缩、病毒扫描或媒体排序。
