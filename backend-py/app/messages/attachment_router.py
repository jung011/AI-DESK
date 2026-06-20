"""attachment endpoint — POST upload + GET download.

채팅 첨부 (옵션 A — 휴먼↔AI). UI 시퀀스:
1) frontend 가 POST /api/attachments (multipart, ownerAgentId) → attachment_id 받음
2) POST /api/messages 에 attachmentIds=[...] 넣어서 send → service 가 link
3) message 응답에 attachments[] 포함 → frontend 가 chip 표시 + GET 다운로드
"""
import io
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.repository import AgentRepository
from app.common.response import ApiEnvelope, fail, ok
from app.core.config import get_settings
from app.core.database import get_db
from app.messages.attachment_models import MessageAttachment
from app.messages.attachment_repository import AttachmentRepository
from app.messages.schemas import AttachmentUploadRs

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=ApiEnvelope[AttachmentUploadRs])
async def upload(
    file: Annotated[UploadFile, File(...)],
    ownerAgentId: Annotated[str, Form(...)],  # noqa: N803
    db: Session = Depends(get_db),
) -> ApiEnvelope[AttachmentUploadRs]:
    settings = get_settings()

    agent_repo = AgentRepository(db)
    owner = agent_repo.find_by_agent_id_any_owner(ownerAgentId)
    if owner is None:
        return fail(404, "owner agent not found")  # type: ignore[return-value]

    blob = await file.read()
    size = len(blob)
    if size == 0:
        return fail(400, "empty file")  # type: ignore[return-value]
    if size > settings.message_attachment_max_bytes:
        return fail(  # type: ignore[return-value]
            413,
            f"파일 크기 한도 초과 ({size} > {settings.message_attachment_max_bytes} bytes)",
        )

    att = MessageAttachment(
        attachment_id=str(uuid.uuid4()),
        message_id=None,
        owner_agent_id=ownerAgentId,
        original_filename=(file.filename or "unnamed"),
        content_type=(file.content_type or "application/octet-stream"),
        size_bytes=size,
        data=blob,
    )
    repo = AttachmentRepository(db)
    repo.insert(att)
    db.commit()
    db.refresh(att)
    log.info(
        "attachment uploaded: id=%s owner=%s name=%s size=%d",
        att.attachment_id, ownerAgentId, att.original_filename, size,
    )
    return ok(
        AttachmentUploadRs(
            attachment_id=att.attachment_id,
            original_filename=att.original_filename,
            content_type=att.content_type,
            size_bytes=att.size_bytes,
        )
    )


@router.get("/{attachment_id}")
async def download(
    attachment_id: str,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    repo = AttachmentRepository(db)
    att = repo.find_by_id(attachment_id)
    if att is None:
        # StreamingResponse 가 default. 404 는 plain JSON envelope 으로 대신.
        from fastapi.responses import JSONResponse
        return JSONResponse(  # type: ignore[return-value]
            status_code=404,
            content={"code": "NA", "message": "attachment not found"},
        )

    # filename 은 latin-1 safe 인코딩 — RFC 5987 filename* 사용으로 utf-8 한글 파일명 보존.
    from urllib.parse import quote
    encoded = quote(att.original_filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        "Content-Length": str(att.size_bytes),
    }
    return StreamingResponse(
        io.BytesIO(att.data),
        media_type=att.content_type or "application/octet-stream",
        headers=headers,
    )
