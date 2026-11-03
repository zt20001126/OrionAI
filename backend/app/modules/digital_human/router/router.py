"""提供数字人会话历史和语音识别/合成 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response

from app.modules.auth.dependencies import validate_origin
from app.modules.digital_human.dependencies.dependencies import (
    CurrentUser,
    DigitalHumanServiceDependency,
)
from app.modules.digital_human.schemas.schemas import (
    DigitalHumanConversationListResponse,
    SynthesisRequest,
    TranscriptionResponse,
)
from app.modules.membership.dependencies import require_membership_access

router = APIRouter(prefix="/digital-human", tags=["digital-human"])
PageLimit = Annotated[int, Query(ge=1, le=100, description="每页条数，最大 100。")]
PageOffset = Annotated[int, Query(ge=0, description="分页偏移量。")]


@router.get("/conversations", response_model=DigitalHumanConversationListResponse)
def list_conversations(
    user: CurrentUser,
    service: DigitalHumanServiceDependency,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> DigitalHumanConversationListResponse:
    """只返回当前用户的数字人技能会话。"""

    return service.list_conversations(user, limit=limit, offset=offset)


@router.post(
    "/speech/recognitions",
    response_model=TranscriptionResponse,
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
async def recognize_speech(
    user: CurrentUser,
    service: DigitalHumanServiceDependency,
    file: Annotated[UploadFile, File(description="短录音文件。")],
) -> TranscriptionResponse:
    """将短录音转成文本；音频仅在本次请求中暂存。"""

    try:
        audio_bytes = await file.read(service.max_audio_bytes + 1)
        text = await service.transcribe(audio_bytes, content_type=file.content_type)
    finally:
        await file.close()
    return TranscriptionResponse(text=text)


@router.post(
    "/speech/syntheses",
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
async def synthesize_speech(
    payload: SynthesisRequest,
    user: CurrentUser,
    service: DigitalHumanServiceDependency,
) -> Response:
    """返回临时 MPEG 音频，不持久化音频或返回上游下载 URL。"""

    audio = await service.synthesize(payload.text)
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
