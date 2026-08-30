export const operationResources = {
  today: 'operations/live-board',
  serviceOrders: 'operations/live-board',
  auditLogs: 'admin/audit-logs',
  feedback: 'admin/v2/feedback',
} as const;

export const operationMenuPaths = ['/today', '/service-positions', '/selection-sessions', '/orders', '/analytics', '/feedback', '/audit-logs'] as const;
