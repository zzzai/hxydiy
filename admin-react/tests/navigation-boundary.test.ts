import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const source = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('新管理端不暴露预约和派单入口', () => {
  const navigation = source('layouts/MainLayout.tsx');
  const permissions = source('auth.ts');
  const today = source('pages/TodayPage.tsx');

  assert.doesNotMatch(navigation, /预约看板|\/reservations/);
  assert.doesNotMatch(permissions, /\/reservations/);
  assert.doesNotMatch(today, /today-appointments|派钟|assignVisit|getTodayAppointments/);
});

test('新管理端不从房间或服务位调用物理资源操作', () => {
  const rooms = source('pages/RoomsPage.tsx');
  const positions = source('pages/ServicePositionsPage.tsx');

  assert.doesNotMatch(rooms, /createAssignment|deleteAssignment|getRoomDetail|技师绑定/);
  assert.doesNotMatch(rooms, /operateRoom|安排入座|结账并清洁|结账并释放|转清洁/);
  assert.doesNotMatch(positions, /confirmPositionDeparture|finishPositionCleaning|确认离位|完成清洁/);
});

test('服务位页面不再包含移动、异常释放或遗留占用清理流程', () => {
  const positions = source('pages/ServicePositionsPage.tsx');

  assert.doesNotMatch(positions, /submitMove|submitForceRelease|openForceRelease/);
  assert.doesNotMatch(positions, /moveAdminOccupancy|forceReleasePosition|retainPositionOccupancy|bulkReleaseOccupancies|getReleaseCandidates/);
  assert.doesNotMatch(positions, /actionMode === '(move|force_release)'|清理遗留占用|释放选中项|异常结束现场流程|调整到其他服务位/);
});

test('旧预约页面已隔离且兼容预约 API 不再导出', () => {
  const api = source('api.ts');

  assert.equal(existsSync(new URL('../src/pages/ReservationsPage.tsx', import.meta.url)), false);
  assert.doesNotMatch(api, /getReservations/);
  assert.doesNotMatch(api, /moveAdminOccupancy|forceReleasePosition|retainPositionOccupancy|bulkReleaseOccupancies/);
});

test('管理端页面按路由懒加载并提供统一加载态', () => {
  const layout = source('layouts/MainLayout.tsx');

  assert.match(layout, /const ProjectsPage = lazy\(\(\) => import\('\.\.\/pages\/ProjectsPage'\)\)/);
  assert.match(layout, /const ProductsPage = lazy\(\(\) => import\('\.\.\/pages\/ProductsPage'\)\)/);
  assert.match(layout, /const TechsPage = lazy\(\(\) => import\('\.\.\/pages\/TechsPage'\)\)/);
  assert.match(layout, /<Suspense fallback=/);
});
