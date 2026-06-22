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
from app.core.database import SessionLocal, get_db
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
async def download(attachment_id: str) -> StreamingResponse:
    """rc47 fix — Depends(get_db) 대신 명시 `with SessionLocal()`.

    옛: db: Session = Depends(get_db) + StreamingResponse 반환 — FastAPI 의 dependency
    cleanup 은 *response body 완전 전송 후* 실행. slow client / 큰 파일 + 트래픽 누적 시
    response lifetime 동안 session 점유 + transaction commit 안 됨 → idle in transaction
    누적 → DB pool 고갈. rc46 audit 가 못 잡은 leak path.

    fix: with-block 으로 *attachment 데이터 메모리 load 후 session close* → StreamingResponse
    body 전송 동안 DB pool 안전 (io.BytesIO 는 메모리 stream).
    """
    with SessionLocal() as db:
        repo = AttachmentRepository(db)
        att = repo.find_by_id(attachment_id)
        if att is None:
            from fastapi.responses import JSONResponse
            return JSONResponse(  # type: ignore[return-value]
                status_code=404,
                content={"code": "NA", "message": "attachment not found"},
            )
        # 메모리 load — session close 후에도 사용 가능한 plain bytes/str.
        data = bytes(att.data)
        filename = att.original_filename
        content_type = att.content_type
        size_bytes = att.size_bytes

    # session 이미 close — StreamingResponse body 전송하는 동안 DB pool 부담 0.
    from urllib.parse import quote
    encoded = quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        "Content-Length": str(size_bytes),
    }
    return StreamingResponse(
        io.BytesIO(data),
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )
