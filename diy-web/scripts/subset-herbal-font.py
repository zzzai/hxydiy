"""Create small OFL font subsets for the herbal selector only."""
from pathlib import Path
import sys
from fontTools import subset
from fontTools.ttLib import TTFont

root = Path(__file__).resolve().parents[1]
target = root / 'public/assets/fonts/herbal-rounded'
text = '先选服务偏好为你推荐更合适的草本与手法木火土金水方舒心放松最近有点忙想一玫瑰花佛合欢皮筋活力久坐站展下桂枝丹参鸡血藤轻盈畅身体沉茯苓薏苡仁陈清润缓清爽爽桑叶菊百温暖养护脚容易凉杜仲寄生淫羊藿，·'
wanted = set(map(ord, text))
covered = set()
rules = []
for source in sorted(Path(sys.argv[1]).rglob('*.woff2')):
    font = TTFont(source)
    chars = wanted.intersection(font.getBestCmap()) - covered
    if not chars:
        continue
    options = subset.Options()
    options.name_IDs = ['*']
    sub = subset.Subsetter(options=options)
    sub.populate(unicodes=chars)
    sub.subset(font)
    for record in font['name'].names:
        if record.nameID in (1, 2, 3, 4, 6, 16, 17):
            value = 'Regular' if record.nameID in (2, 17) else 'HxyHerbalRounded'
            record.string = value.encode(record.getEncoding())
    name = f'herbal-{len(rules)}.woff2'
    font.save(target / name)
    ranges = ','.join(f'U+{c:X}' for c in sorted(chars))
    rules.append(f"@font-face {{ font-family: HxyHerbalRounded; src: url('/assets/fonts/herbal-rounded/{name}') format('woff2'); font-style: normal; font-weight: 400; font-display: swap; unicode-range: {ranges}; }}")
    covered.update(chars)
if wanted - covered:
    raise RuntimeError(f'Missing characters: {sorted(wanted - covered)}')
(root / 'src/herbal-font.css').write_text('\n'.join(rules) + '\n', encoding='utf-8')
print(f'{len(covered)} characters, {len(rules)} subsets, {sum(p.stat().st_size for p in target.glob("*.woff2"))} bytes')
