"""Weekly store inspection metrics from observed business days and original evidence."""
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.domain.inspection_checklist import CHECKLISTS
from app.models import DailyAreaPhoto, DailyAreaPhotoReview, DailyStoreCheckin, MediaAsset, Store
from app.services.inspection_issues import PROBLEMS, STORE_CODES, followups_by_root, roots_query, verdict

SHANGHAI = ZoneInfo("Asia/Shanghai")


def utc(value):
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def weekly_due(now):
    local = now.astimezone(SHANGHAI)
    monday = local.date() - timedelta(days=local.weekday())
    if local < datetime.combine(monday, time(9), SHANGHAI):
        monday -= timedelta(days=7)
    return monday - timedelta(days=7)


def summarize_week(db, start: date, *, as_of: datetime):
    if start.weekday() != 0:
        raise ValueError("The reporting week must begin on Monday.")
    stop = start + timedelta(days=7)
    cutoff = min(datetime.combine(stop, time.min, SHANGHAI), as_of)
    beginning = datetime.combine(start, time.min, SHANGHAI)
    result = {}
    for store in db.scalars(select(Store).where(Store.store_code.in_(STORE_CODES)).order_by(Store.id)):
        data = dict(store=store.name, submitted=0, draft=0, points=0, expected=0, photos=0,
                    passed=0, fix=0, retake=0, unreviewed=0, failed=0, legacy_manual=0,
                    closed=0, outstanding=0, repeated=[], draft_points=0, draft_expected=0, no_record=0)
        days = db.scalars(select(DailyStoreCheckin).where(
            DailyStoreCheckin.store_id == store.id, DailyStoreCheckin.business_date >= start,
            DailyStoreCheckin.business_date < stop, DailyStoreCheckin.created_at < cutoff)).all()
        submitted_ids = []
        for day in days:
            if day.submitted_at is not None and utc(day.submitted_at) < cutoff and day.status == "submitted":
                submitted_ids.append(day.id)
                data["expected"] += len(CHECKLISTS[day.checklist_version or 1])
            else:
                data["draft"] += 1
                data["draft_expected"] += len(CHECKLISTS[day.checklist_version or 1])
        data["submitted"] = len(submitted_ids)
        elapsed = max(0, (min(stop, as_of.astimezone(SHANGHAI).date() + timedelta(days=1)) - start).days)
        data["no_record"] = max(0, elapsed - len({day.business_date for day in days}))
        submitted_set = set(submitted_ids)
        draft_coverage = set()
        coverage = set()
        repeat_days = defaultdict(set)
        if days:
            records = db.execute(select(DailyAreaPhoto, DailyAreaPhotoReview, DailyStoreCheckin.business_date)
                .select_from(DailyAreaPhoto).join(DailyStoreCheckin, DailyStoreCheckin.id == DailyAreaPhoto.checkin_id)
                .join(MediaAsset, MediaAsset.id == DailyAreaPhoto.media_id)
                .outerjoin(DailyAreaPhotoReview, (DailyAreaPhotoReview.photo_id == DailyAreaPhoto.id)
                           & (DailyAreaPhotoReview.media_id == DailyAreaPhoto.media_id))
                .where(DailyAreaPhoto.checkin_id.in_([day.id for day in days]), MediaAsset.store_id == store.id,
                       MediaAsset.deleted_at.is_(None), MediaAsset.purpose == "daily_area",
                       MediaAsset.media_type == "image", MediaAsset.created_at < cutoff))
            for photo, review, day in records:
                if photo.checkin_id not in submitted_set:
                    draft_coverage.add((day, photo.area))
                    continue
                coverage.add((day, photo.area))
                data["photos"] += 1
                value = verdict(review) if review and review.finished_at and utc(review.finished_at) < cutoff else None
                category = "passed" if value == "pass" else value if value in PROBLEMS else "unreviewed"
                data[category] += 1
                if review and review.state == "failed" and review.finished_at and utc(review.finished_at) < cutoff:
                    data["failed"] += 1
                if value == "fix":
                    repeat_days[photo.area].add(day)
                if review and review.manual_verdict and review.manual_at and utc(review.manual_at) < cutoff:
                    data["legacy_manual"] += 1
        data["points"] = len(coverage)
        data["draft_points"] = len(draft_coverage)
        data["repeated"] = [(CHECKLISTS[3][area], len(observed)) for area, observed in
                            sorted(repeat_days.items(), key=lambda pair: (-len(pair[1]), pair[0])) if len(observed) > 1]
        roots = db.execute(roots_query(cutoff).where(
            DailyStoreCheckin.store_id == store.id, DailyAreaPhotoReview.finished_at < cutoff)).all()
        chain = followups_by_root(db, [root.id for root, *_ in roots])
        for root, *_ in roots:
            completed = next((review for _, review, _ in chain[root.id]
                              if verdict(review) == "pass" and review.finished_at and utc(review.finished_at) < cutoff), None)
            if completed is None:
                data["outstanding"] += 1
            elif utc(completed.finished_at) >= beginning:
                data["closed"] += 1
        result[store.store_code] = data
    return result


def weekly_text(db, start, *, as_of):
    this = summarize_week(db, start, as_of=as_of)
    previous = summarize_week(db, start - timedelta(days=7), as_of=as_of)
    lines = [f"荷小悦巡检周报 · {start:%m.%d}—{start + timedelta(days=6):%m.%d}"]
    for code, row in this.items():
        lines.extend(["", row["store"], f"已提交 {row['submitted']} 天，草稿 {row['draft']} 天，无日报记录 {row['no_record']} 天。"])
        if row["submitted"]:
            lines.append(f"已提交日报覆盖 {row['points']}/{row['expected']} 个拍摄点。"
                         f"初审 {row['photos']} 张，通过 {row['passed']}、需整改 {row['fix']}、"
                         f"需补拍 {row['retake']}、审核未完成 {row['unreviewed']}（含审核失败 {row['failed']}）。")
        else:
            lines.append("本周没有已提交日报，缺少现场质量数据。")
        if row["draft"]:
            lines.append(f"草稿已拍 {row['draft_points']}/{row['draft_expected']} 个点位。")
        lines.append(f"系统复查完成 {row['closed']} 项，期末仍待处理 {row['outstanding']} 项。")
        if row["legacy_manual"]:
            lines.append(f"旧版人工更正 {row['legacy_manual']} 张，单独列示。")
        if row["repeated"]:
            label, days = row["repeated"][0]
            lines.append(f"下周优先检查{label}，在 {days} 个不同营业日发现需整改问题。")
        elif row["outstanding"]:
            lines.append("下周优先完成尚未通过复查的点位。")
        old = previous.get(code, {})
        judged = row["passed"] + row["fix"]
        old_judged = old.get("passed", 0) + old.get("fix", 0)
        if judged and old_judged:
            lines.append(f"能判断现场的照片中，需整改 {row['fix']}/{judged} 张，上周 {old['fix']}/{old_judged} 张。")
    return "\n".join(lines)
