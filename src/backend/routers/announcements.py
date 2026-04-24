"""
Announcement endpoints for the High School Management System API
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    expires_at: str = Field(min_length=1)
    starts_at: Optional[str] = None


def _require_signed_in_user(username: Optional[str]) -> Dict[str, Any]:
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = teachers_collection.find_one({"_id": username})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return user


def _parse_iso_datetime(raw_value: str, field_name: str) -> datetime:
    value = raw_value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be a valid ISO datetime string"
        ) from exc


def _serialize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", ""),
        "message": doc.get("message", ""),
        "starts_at": doc.get("starts_at"),
        "expires_at": doc.get("expires_at"),
        "created_by": doc.get("created_by", ""),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at")
    }


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_announcements(active_only: bool = Query(True)) -> List[Dict[str, Any]]:
    now_iso = datetime.utcnow().isoformat()
    query: Dict[str, Any] = {}

    if active_only:
        query = {
            "expires_at": {"$gte": now_iso},
            "$or": [
                {"starts_at": None},
                {"starts_at": {"$exists": False}},
                {"starts_at": ""},
                {"starts_at": {"$lte": now_iso}}
            ]
        }

    docs = announcements_collection.find(query).sort("expires_at", 1)
    return [_serialize_announcement(doc) for doc in docs]


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    _require_signed_in_user(teacher_username)

    expires_dt = _parse_iso_datetime(payload.expires_at, "expires_at")
    starts_dt = None
    starts_iso = None

    if payload.starts_at:
        starts_dt = _parse_iso_datetime(payload.starts_at, "starts_at")
        starts_iso = starts_dt.isoformat()

    if starts_dt and starts_dt > expires_dt:
        raise HTTPException(
            status_code=400,
            detail="starts_at must be earlier than or equal to expires_at"
        )

    now_iso = datetime.utcnow().isoformat()
    document = {
        "title": payload.title.strip(),
        "message": payload.message.strip(),
        "starts_at": starts_iso,
        "expires_at": expires_dt.isoformat(),
        "created_by": teacher_username,
        "created_at": now_iso,
        "updated_at": now_iso
    }

    result = announcements_collection.insert_one(document)
    inserted = announcements_collection.find_one({"_id": result.inserted_id})
    if not inserted:
        raise HTTPException(status_code=500, detail="Failed to create announcement")

    return _serialize_announcement(inserted)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    _require_signed_in_user(teacher_username)

    try:
        doc_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    expires_dt = _parse_iso_datetime(payload.expires_at, "expires_at")
    starts_dt = None
    starts_iso = None

    if payload.starts_at:
        starts_dt = _parse_iso_datetime(payload.starts_at, "starts_at")
        starts_iso = starts_dt.isoformat()

    if starts_dt and starts_dt > expires_dt:
        raise HTTPException(
            status_code=400,
            detail="starts_at must be earlier than or equal to expires_at"
        )

    updates = {
        "title": payload.title.strip(),
        "message": payload.message.strip(),
        "starts_at": starts_iso,
        "expires_at": expires_dt.isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    result = announcements_collection.update_one({"_id": doc_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": doc_id})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to load updated announcement")

    return _serialize_announcement(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    _require_signed_in_user(teacher_username)

    try:
        doc_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    result = announcements_collection.delete_one({"_id": doc_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
