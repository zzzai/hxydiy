"""Project a photo issue and its ordered system rechecks without changing its original inspection."""
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.models import DailyAreaPhoto, DailyAreaPhotoReview, DailyStoreCheckin, InspectionFollowup, MediaAsset, Store


STORE_CODES = ("hxy-anyang-ziwei-001", "hxy-anyang-huafu-002")
PROBLEMS = ("fix", "retake")


def verdict(review):
    return (review.result or {}).get("verdict") if review.state == "done" else None


def roots_query(now=None):
    review, photo, day, media = DailyAreaPhotoReview, DailyAreaPhoto, DailyStoreCheckin, MediaAsset
    start = settings.inspection_workflow_from
    query = (select(review, photo, day, media)
             .select_from(review).join(photo, photo.id == review.photo_id)
             .join(day, day.id == photo.checkin_id).join(Store, Store.id == day.store_id)
             .join(media, media.id == review.media_id)
             .where(Store.store_code.in_(STORE_CODES), photo.media_id == review.media_id,
                    media.store_id == day.store_id, media.purpose == "daily_area", media.media_type == "image",
                    media.deleted_at.is_(None), review.state == "done", review.manual_verdict.is_(None),
                    review.result["verdict"].as_string().in_(PROBLEMS),
                    day.created_at >= (now or datetime.now(UTC)) - timedelta(days=90)))
    if start is None:
        return query.where(False)
    return query.where(media.created_at >= start)


def followups_by_root(db, root_ids):
    grouped = defaultdict(list)
    if root_ids:
        records = db.execute(select(InspectionFollowup, DailyAreaPhotoReview, MediaAsset)
            .join(DailyAreaPhotoReview, DailyAreaPhotoReview.id == InspectionFollowup.review_id)
            .join(MediaAsset, MediaAsset.id == DailyAreaPhotoReview.media_id)
            .where(InspectionFollowup.root_id.in_(root_ids)).order_by(InspectionFollowup.sequence))
        for link, review, media in records:
            grouped[link.root_id].append((link, review, media))
    return grouped


def latest_review(root, history):
    return history[-1][1] if history else root


def issue_status(review):
    value = verdict(review)
    if value == "pass":
        return "closed"
    if value in PROBLEMS:
        return value
    if review.state in {"pending", "running"}:
        return "reviewing"
    return "unreviewed"


def followup_media_for_checkin(db, checkin):
    return db.scalars(select(MediaAsset).join(DailyAreaPhotoReview, DailyAreaPhotoReview.media_id == MediaAsset.id)
                      .join(InspectionFollowup, InspectionFollowup.review_id == DailyAreaPhotoReview.id)
                      .join(DailyAreaPhoto, DailyAreaPhoto.id == DailyAreaPhotoReview.photo_id)
                      .where(DailyAreaPhoto.checkin_id == checkin.id, MediaAsset.store_id == checkin.store_id,
                             MediaAsset.purpose == "daily_area", MediaAsset.media_type == "image")).all()


def lock_root(db, store_id, root_id):
    return db.execute(roots_query().where(DailyAreaPhotoReview.id == root_id, DailyStoreCheckin.store_id == store_id)
                      .with_for_update(of=DailyStoreCheckin)).one_or_none()
