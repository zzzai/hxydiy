export function membershipVerificationView(hasScannedMember: boolean, blockedPositionCount: number) {
  const view: {
    showSelection: boolean;
    primaryAction: '打开摄像头扫码' | '确认绑定本次选单';
    blockedMessage?: string;
  } = {
    showSelection: hasScannedMember,
    primaryAction: hasScannedMember ? '确认绑定本次选单' : '打开摄像头扫码',
  };
  if (blockedPositionCount > 0) view.blockedMessage = `${blockedPositionCount} 个服务位待店长核对，暂不可绑定会员。`;
  return view;
}
