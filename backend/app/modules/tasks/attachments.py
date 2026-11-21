"""Secure attachments: allow-listed types verified by file signature, size cap, random storage names,
authorization re-checked on every download, always served as a download (never rendered)."""

import hashlib
import os
import re
import secrets
from pathlib import Path

from fastapi import Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.rbac.policy import Principal
from app.modules.tasks.models import Task, TaskAttachment

ZIP, OLE = b"PK\x03\x04", b"\xd0\xcf\x11\xe0"
# extension -> (required leading bytes or None for plain text, mime type)
ALLOWED: dict[str, tuple[bytes | None, str]] = {
    ".pdf": (b"%PDF", "application/pdf"),
    ".png": (b"\x89PNG\r\n\x1a\n", "image/png"),
    ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
    ".jpeg": (b"\xff\xd8\xff", "image/jpeg"),
    ".gif": (b"GIF8", "image/gif"),
    ".zip": (ZIP, "application/zip"),
    ".docx": (ZIP, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xlsx": (ZIP, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".pptx": (ZIP, "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ".doc": (OLE, "application/msword"),
    ".xls": (OLE, "application/vnd.ms-excel"),
    ".txt": (None, "text/plain"),
    ".csv": (None, "text/csv"),
}


def upload_root() -> Path:
    root = Path(get_settings().upload_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[3] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def clean_name(name: str) -> str:
    base = os.path.basename((name or "file").replace("\\", "/"))
    base = re.sub(r"[\x00-\x1f\x7f\"<>|:*?]", "_", base).strip(". ") or "file"
    return base[:200]


def path_for(key: str) -> Path:
    return upload_root() / key[:2] / key


async def save_upload(db: Session, p: Principal, task: Task, file: UploadFile, request: Request) -> TaskAttachment:
    name = clean_name(file.filename or "")
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED:
        raise AppError("FILE_TYPE_NOT_ALLOWED", f"Allowed file types: {', '.join(sorted(ALLOWED))}", 415)
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError("FILE_TOO_LARGE", f"Files can be at most {get_settings().max_upload_mb} MB", 413)
    if not data:
        raise AppError("EMPTY_FILE", "The file is empty", 422)
    signature, mime = ALLOWED[ext]
    if signature is not None and not data.startswith(signature):
        raise AppError("FILE_CONTENT_MISMATCH", "The file content does not match its extension", 415)
    if signature is None and b"\x00" in data[:8192]:
        raise AppError("FILE_CONTENT_MISMATCH", "The file content does not match its extension", 415)
    key = secrets.token_hex(20)
    target = path_for(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    att = TaskAttachment(task_id=task.id, uploaded_by_user_id=p.user.id, original_name=name, stored_key=key,
                         mime_type=mime, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())  # fmt: skip
    db.add(att)
    db.flush()
    audit.log(db, p.user.id, "TASK_ATTACHMENT_ADDED", "task", task.id, after={"name": name, "size": len(data)},
              request=request, task_id=task.id)  # fmt: skip
    return att
