---
name: 荷小悦技师服务记录本地原型
description: 从本目录 index.html 提取的白底深绿业务界面记录
colors:
  ink: "#193e33"
  muted: "#596b63"
  line: "#dbe4de"
  wash: "#edf4ef"
  surface: "#ffffff"
  canvas: "#f1f3f1"
  primary-hover: "#285b48"
  focus: "#8a6b29"
typography:
  body:
    fontFamily: "system-ui, 'Microsoft YaHei', sans-serif"
    fontSize: "16px"
    lineHeight: 1.6
  headline:
    fontSize: "25px"
    lineHeight: 1.4
  title:
    fontSize: "18px"
rounded:
  control: "8px"
spacing:
  chip-gap: "8px"
  section: "24px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
---

# Design System: 荷小悦技师服务记录本地原型

## Overview

本记录仅约束本目录原型，以现有 `index.html` 为提取依据。沿用白色内容区域和深绿色操作，文字直接、信息紧凑；没有另行批准的视觉效果图或新品牌方案。产品范围见 `PRODUCT.md`，不将页面布局升级为全仓库设计规则。

## Colors

深绿用于正文、主要操作与选中状态，灰绿用于次要说明，浅绿用于反馈和悬停；白色承载主要内容，浅灰仅作为桌面外部画布。暖金焦点轮廓帮助键盘定位。

## Typography

使用系统中文无衬线字体。正文采用 body；页面标题采用 headline，手机宽度下降至 24px；分区标题采用 title。说明和字段标签分别使用较小字号，层级不依赖颜色独立表达。

## Layout

单列容器最大宽度 640px，桌面上下外边距 24px。主内容内边距 24px；640px 及以下铺满屏幕，横向内边距调整为 20px。选择项换行并保持 chip-gap；部位和左右侧字段采用两个等宽列。分区以 section 间距和细分隔线组织，不使用仪表盘卡片网格。

## Elevation & Depth

未使用阴影。通过白底、细边框、浅色嵌套区域区分层级。保存反馈仅在允许动态效果时执行 0.2 秒背景色动画；扩展值记于同目录 `.impeccable/design.json`。

## Shapes

按钮、输入和嵌套区域使用 control 圆角。导航使用平直底边，当前页有 3px 深绿下划线。交互控件最小高度 44px；文本域最小高度 100px，可垂直拉伸。

## Components

- 按钮：深绿主操作、白底细边框次操作；主要操作悬停使用 primary-hover。禁用状态同时取消指针提示。
- 选择项：沿用按钮外形，用 `aria-pressed` 和深绿填充共同表达选择，重复点击可取消。
- 输入：白底细边框、满宽布局；键盘焦点使用 2px 暖金轮廓及 3px 外偏移。
- 导航：三项横排文字，当前页加粗并显示底边；切页后焦点移至页面标题。
- 容器：主要内容保持平面分区；条件补充区使用浅色背景及 16px 内边距。
- 状态：保存反馈使用浅绿区域；错误使用文字与错误色共同表达，不只靠颜色。

## Do's and Don'ts

- Do 保持白色内容区域、深绿色主要操作及明确的键盘焦点。
- Do 从原型实际代码复核尺寸和状态，修改视觉实现时同步本记录。
- Don't 将此原型视为生产组件库或全仓库视觉规范。
- Don't 将虚构参考、模拟保存或示意权限描述为已上线能力。
