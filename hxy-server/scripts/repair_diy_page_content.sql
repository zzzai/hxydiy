BEGIN;

UPDATE page_contents
SET
  title = '到店选项目',
  subtitle = '按需要，自由搭配',
  promo_banners = '[
    {"eyebrow":"今日推荐","title":"草本泡脚","project_code":"hxy-qiqing-30"},
    {"eyebrow":"主力推荐","title":"荷小推","project_code":"hxy-tuina-70"},
    {"eyebrow":"主力推荐","title":"精油SPA","project_code":"hxy-spa-90"},
    {"eyebrow":"套盒调理","title":"功夫调理","project_code":"hxy-taoke-60"}
  ]'::json,
  tea_options = '[
    {"name":"老姜茶","note":"辛香温润","description":"姜香温润，适合偏爱暖香口感。","image_url":"/assets/fresh-ginger.jpg"},
    {"name":"陈皮茶","note":"清香顺口","description":"陈皮清香，入口顺和，适合日常慢饮。","image_url":"/assets/hxy-herbal-tea-cup.webp"},
    {"name":"玫瑰茶","note":"柔和花香","description":"花香柔和，口感清雅，适合偏爱轻盈香气。","image_url":"/assets/home-herbal-wellness-tea.webp"}
  ]'::json,
  coupon_prompt = '{"title":"登录领取到店礼","body":"手机号登录后领取，优惠券保存到账号"}'::json,
  brand_story = '{"title":"把服务做到身边","body":"从真实需求出发，用好服务赢得信任。"}'::json,
  published = TRUE,
  updated_at = NOW()
WHERE store_id = 1 AND page_key = 'diy-home';

COMMIT;
