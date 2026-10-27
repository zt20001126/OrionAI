"""提供登录保护的简历编辑、照片和 PDF 接口。"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.modules.auth.dependencies import get_current_user, validate_origin
from app.modules.auth.models import User
from app.modules.resume.dependencies import ResumeServiceDependency
from app.modules.resume.errors import ResumeError
from app.modules.resume.schemas import MAX_PHOTO_BYTES, ResumeSaveRequest

router = APIRouter(prefix="/resume", tags=["resume"])
CurrentUser = Annotated[User, Depends(get_current_user)]
_PHOTO_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _handle_resume_error(error: ResumeError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from None


@router.get("")
def get_resume(user: CurrentUser, service: ResumeServiceDependency) -> dict[str, object]:
    try:
        return service.get_resume(user.id).model_dump(mode="json")
    except ResumeError as error:
        _handle_resume_error(error)


@router.put("", dependencies=[Depends(validate_origin)])
def save_resume(
    payload: ResumeSaveRequest,
    user: CurrentUser,
    service: ResumeServiceDependency,
) -> dict[str, object]:
    try:
        return service.save_resume(user.id, payload).model_dump(mode="json")
    except ResumeError as error:
        _handle_resume_error(error)


@router.post("/photo", dependencies=[Depends(validate_origin)])
async def upload_resume_photo(
    user: CurrentUser,
    service: ResumeServiceDependency,
    file: Annotated[UploadFile, File(description="PNG/JPEG 照片，最大 5 MiB")],
) -> dict[str, object]:
    try:
        data = await file.read(MAX_PHOTO_BYTES + 1)
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="照片不能超过 5 MiB。")
        return service.upload_photo(user.id, data).model_dump(mode="json")
    except ResumeError as error:
        _handle_resume_error(error)
    finally:
        await file.close()


@router.get("/photo")
def get_resume_photo(user: CurrentUser, service: ResumeServiceDependency) -> Response:
    try:
        data, mime_type = service.get_saved_photo(user.id)
    except ResumeError as error:
        _handle_resume_error(error)
    return Response(
        content=data,
        media_type=mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/photo", dependencies=[Depends(validate_origin)])
def delete_staged_resume_photo(
    photo_id: str,
    user: CurrentUser,
    service: ResumeServiceDependency,
) -> dict[str, object]:
    if not _PHOTO_ID_PATTERN.fullmatch(photo_id):
        raise HTTPException(status_code=422, detail="照片标识格式无效。")
    try:
        service.delete_staged_photo(user.id, photo_id)
    except ResumeError as error:
        _handle_resume_error(error)
    return {"photo_id": photo_id, "deleted": True}


@router.get("/export/pdf")
def export_resume_pdf(user: CurrentUser, service: ResumeServiceDependency) -> Response:
    try:
        pdf_bytes = service.export_pdf(user.id)
    except ResumeError as error:
        _handle_resume_error(error)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="resume.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
