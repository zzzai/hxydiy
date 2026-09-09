/** Framer Motion 共用过渡配置（只动 transform/opacity，不触碰现有 CSS）。 */

export type MotionPreset = {
  initial: { opacity: number; x?: number; y?: number; scale?: number };
  animate: { opacity: number; x?: number; y?: number; scale?: number };
  exit: { opacity: number; x?: number; y?: number; scale?: number };
  transition: { duration: number; delay?: number; ease: 'easeOut' | 'linear' };
};

const normalTransition = { duration: 0.18, ease: 'easeOut' as const };

/** 系统减少动态效果时，保留短淡入淡出，移除位移、缩放和错峰。 */
export function motionForPreference(preset: MotionPreset, reduced: boolean | null): MotionPreset {
  if (!reduced) return preset;
  return {
    initial: { opacity: 0 },
    animate: { opacity: 1 },
    exit: { opacity: 0 },
    transition: { duration: 0.15, delay: 0, ease: 'linear' },
  };
}

export const fadeInMotion: MotionPreset = {
  initial: { opacity: 0, y: 8, scale: 0.96 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: 8 },
  transition: normalTransition,
};

/** 详情页轻推入，保持内容稳定，不参与布局尺寸动画。 */
export const detailMotion: MotionPreset = {
  initial: { opacity: 0, x: 18 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: 18 },
  transition: { duration: 0.2, ease: 'easeOut' },
};

/** 选项点击反馈仅使用短暂缩放与透明度。 */
export const selectionFeedbackMotion: MotionPreset = {
  initial: { opacity: 0.86, scale: 0.985 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0.86, scale: 0.985 },
  transition: normalTransition,
};

/** 底部清单从底部轻推入。 */
export const sheetMotion: MotionPreset = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 24 },
  transition: { duration: 0.22, ease: 'easeOut' },
};

/** 菜单权益区在内容准备好后轻淡入。 */
export const promoStripMotion: MotionPreset = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 8 },
  transition: { duration: 0.2, ease: 'easeOut' },
};

/** 金额和数量变更只用短距离替换，不推动整个底栏。 */
export const valueChangeMotion: MotionPreset = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.16, ease: 'easeOut' },
};

/** 选购清单分段进入；最多四段，避免内容越多延迟越长。 */
export function sheetSectionMotion(index: number): MotionPreset {
  return {
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: 8 },
    transition: { duration: 0.18, delay: Math.min(index, 3) * 0.04, ease: 'easeOut' },
  };
}

/** Toast 轻微上移淡入。 */
export const toastMotion: MotionPreset = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 6 },
  transition: normalTransition,
};
