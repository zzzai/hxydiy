# 发布检查清单

每次生产发布复制本清单到发布记录，不允许口头确认。

## 1. 版本

- [ ] 发布 commit 来自最新 `main`
- [ ] 本地工作区 clean
- [ ] commit SHA：
- [ ] CI run：
- [ ] PR：

## 2. 设计

- [ ] UI 改动附 390px 截图
- [ ] 后台改动附 1280px 截图
- [ ] 改前/改后对比
- [ ] 空/错/加载状态
- [ ] 符合 `DESIGN.md`

## 3. 资产

- [ ] 项目主图/详情图已登记
- [ ] `diy-web/tests/project-assets.test.ts` 通过
- [ ] 二进制文件未被 CRLF 处理
- [ ] 没有临时借用未登记图片

## 4. 测试

- [ ] `make test-api`
- [ ] `make test-web`
- [ ] `make test-admin`
- [ ] `npm run build`（diy-web）
- [ ] `npm run build`（admin-react）
- [ ] 静态合同 / 空白检查 / 凭据扫描

## 5. 数据库

- [ ] 无迁移
- [ ] 有迁移，文件名：
- [ ] 已在 `deploy/diy/deploy-production.sh` approved 列表
- [ ] 备份完成
- [ ] 回滚 SQL/步骤：

## 6. 发布

- [ ] GitHub Actions `Deploy Production` 输入：
  - commit_sha：
  - ci_run_id：
- [ ] Deploy run：
- [ ] release：
- [ ] `/api/v1/health` = ok/production
- [ ] 关键页面抽查：
  - [ ] 顾客菜单
  - [ ] 项目详情
  - [ ] 券包/领券
  - [ ] 店长今日
  - [ ] 店长经营
  - [ ] 后台列表

## 7. 失败处理

- [ ] 回滚到上一 release
- [ ] 记录失败原因
- [ ] 不在失败版本上继续叠加改动
