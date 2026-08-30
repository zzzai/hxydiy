/** Framer Motion 共用过渡配置（只动 transform/opacity，不触碰现有 CSS）。 */

export const fadeInMotion = {
  initial: { opacity: 0, y: 8, scale: 0.96 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: 8 },
};

/** 详情页轻推入，保持内容稳定，不参与布局尺寸动画。 */
export const detailMotion = {
  initial: { opacity: 0, x: 18 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: 18 },
};

/** 选项点击反馈仅使用短暂缩放与透明度。 */
export const selectionFeedbackMotion = {
  initial: { opacity: 0.86, scale: 0.985 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0.86, scale: 0.985 },
};

/** 底部清单从底部轻推入。 */
export const sheetMotion = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 24 },
};

/** Toast 轻微上移淡入。 */
export const toastMotion = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 6 },
};
