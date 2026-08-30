import type { Occupancy } from './api';

type CustomerServiceStatusInput = {
  boot: string;
  hasSession: boolean;
  hasToken: boolean;
  readOnly: boolean;
  hasSubmittedService?: boolean;
};

export function shouldPollCustomerServiceStatus(input: CustomerServiceStatusInput): boolean {
  if (!input.hasSession || !input.hasToken) return false;
  return input.boot === 'submitted'
    || (input.boot === 'ready' && (input.readOnly || input.hasSubmittedService === true));
}

export function customerServiceProgress(occupancyStatus: Occupancy['status'] | null | undefined) {
  switch (occupancyStatus) {
    case 'in_service':
      return {
        eyebrow: '服务进行中',
        title: '已开始为您服务',
        message: '技师正在为您服务，如有需要可与现场工作人员沟通。',
        browseLabel: '服务中，可查看本次清单',
      } as const;
    case 'post_service_present':
    case 'cleaning':
    case 'released':
      return {
        eyebrow: '本次服务已结束',
        title: '感谢本次体验',
        message: '本次服务已完成，欢迎留下您的评价。',
        browseLabel: '服务已结束，可查看本次清单',
      } as const;
    case 'waiting_service':
      return {
        eyebrow: '已提交前台',
        title: '选单已送达门店',
        message: '已收到您的服务需求，工作人员会尽快与您确认。',
        browseLabel: '已提交前台，可查看本次清单',
      } as const;
    default:
      return {
        eyebrow: '选单已送达门店',
        title: '选单已送达门店',
        message: '已收到您的服务需求，工作人员会尽快与您确认。',
        browseLabel: '已提交前台，可查看本次清单',
      } as const;
  }
}
