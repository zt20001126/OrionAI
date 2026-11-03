"""编排数字人历史读取、语音识别与语音合成。"""

import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.models import User
from app.modules.digital_human.constants import (
    DIGITAL_HUMAN_MAX_AUDIO_BYTES,
    DIGITAL_HUMAN_MAX_TTS_TEXT_CHARS,
)
from app.modules.digital_human.providers.asr import AsrProvider, BailianAsrProvider
from app.modules.digital_human.providers.errors import DigitalHumanProviderError
from app.modules.digital_human.providers.tts import BailianTtsProvider, TtsProvider
from app.modules.digital_human.repository import repository
from app.modules.digital_human.schemas.schemas import (
    DigitalHumanConversationListResponse,
    DigitalHumanConversationSummary,
)
from app.modules.digital_human.service.errors import (
    DigitalHumanPayloadTooLargeError,
    DigitalHumanUnavailableError,
    DigitalHumanValidationError,
)

logger = logging.getLogger(__name__)
SUPPORTED_AUDIO_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/opus",
}


class DigitalHumanService:
    """数字人业务入口；复用既有会话模型，只提供技能过滤读取和语音处理。"""

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        asr_provider: AsrProvider | None = None,
        tts_provider: TtsProvider | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._asr_provider = asr_provider or BailianAsrProvider(settings)
        self._tts_provider = tts_provider or BailianTtsProvider(settings)

    @property
    def max_audio_bytes(self) -> int:
        """返回 Router 用于限制 multipart 读取大小的边界。"""

        return DIGITAL_HUMAN_MAX_AUDIO_BYTES

    def list_conversations(
        self,
        user: User,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> DigitalHumanConversationListResponse:
        """返回分页后的当前用户数字人会话。"""

        if not 1 <= limit <= 100 or offset < 0:
            raise DigitalHumanValidationError("分页参数无效。")
        try:
            total_count = repository.count_conversations(self._session, user.id)
            conversations = repository.list_conversations(
                self._session,
                user.id,
                limit=limit,
                offset=offset,
            )
        except SQLAlchemyError:
            self._session.rollback()
            logger.exception("digital_human_conversation_list_failed user_id=%s", user.id)
            raise DigitalHumanUnavailableError("会话记录暂时无法读取，请稍后重试。") from None
        return DigitalHumanConversationListResponse(
            items=[
                DigitalHumanConversationSummary(
                    id=str(conversation.id),
                    skill_code=conversation.skill_code,
                    title=conversation.title,
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                )
                for conversation in conversations
            ],
            limit=limit,
            offset=offset,
            total_count=total_count,
        )

    async def transcribe(self, audio: bytes, *, content_type: str | None) -> str:
        """验证短录音边界并返回不持久化的 ASR 文本。"""

        if not audio:
            raise DigitalHumanValidationError("录音内容为空。")
        if len(audio) > DIGITAL_HUMAN_MAX_AUDIO_BYTES:
            raise DigitalHumanPayloadTooLargeError
        normalized_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
        if normalized_type not in SUPPORTED_AUDIO_TYPES:
            raise DigitalHumanValidationError("当前录音格式不受支持。")
        try:
            text = await self._asr_provider.transcribe(audio, content_type=normalized_type)
        except DigitalHumanProviderError as error:
            logger.warning("digital_human_asr_failed error_type=%s", type(error).__name__)
            raise DigitalHumanUnavailableError(str(error)) from None
        if not text.strip():
            raise DigitalHumanValidationError("没有识别到语音内容，请重新录制。")
        return text.strip()

    async def synthesize(self, text: str) -> bytes:
        """限制 TTS 文本长度并返回临时音频字节。"""

        normalized_text = text.strip()
        if not normalized_text:
            raise DigitalHumanValidationError("语音合成文本不能为空。")
        if len(normalized_text) > DIGITAL_HUMAN_MAX_TTS_TEXT_CHARS:
            raise DigitalHumanValidationError("语音合成文本超过长度限制。")
        try:
            return await self._tts_provider.synthesize(normalized_text)
        except DigitalHumanProviderError as error:
            logger.warning("digital_human_tts_failed error_type=%s", type(error).__name__)
            raise DigitalHumanUnavailableError(str(error)) from None
