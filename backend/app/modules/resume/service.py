"""编排简历校验、保存、照片、PDF 和 Agent 所需事实投影。"""

import logging
import re
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.resume import repository
from app.modules.resume.errors import (
    ResumeConflictError,
    ResumeNotFoundError,
    ResumePhotoError,
    ResumePhotoStorageError,
    ResumeUnavailableError,
)
from app.modules.resume.models import Resume
from app.modules.resume.pdf_renderer import PlaywrightResumePdfRenderer
from app.modules.resume.photo_storage import ResumePhotoStorage
from app.modules.resume.schemas import (
    MAX_PHOTO_BYTES,
    JobResumeSnapshot,
    ResumeContent,
    ResumePhotoUploadResponse,
    ResumeResponse,
    ResumeSaveRequest,
    ResumeStyleConfig,
    document_text,
)

logger = logging.getLogger(__name__)
_PHOTO_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class ResumeApplicationService:
    """在每个调用中使用认证依赖传入的当前用户 ID。"""

    def __init__(
        self,
        session: Session,
        *,
        photo_storage: ResumePhotoStorage,
        pdf_renderer: PlaywrightResumePdfRenderer | None = None,
    ) -> None:
        self._session = session
        self._photo_storage = photo_storage
        self._pdf_renderer = pdf_renderer or PlaywrightResumePdfRenderer()

    def get_resume(self, user_id: int) -> ResumeResponse:
        row = self._get_resume(user_id)
        if row is None:
            return ResumeResponse(
                exists=False,
                content=ResumeContent(),
                style_config=ResumeStyleConfig(),
            )
        try:
            return ResumeResponse(
                exists=True,
                content=ResumeContent.model_validate(row.content),
                style_config=ResumeStyleConfig.model_validate(row.style_config),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        except ValidationError as error:
            logger.warning("resume_record_invalid error_type=%s", type(error).__name__)
            raise ResumeUnavailableError from None

    def save_resume(self, user_id: int, payload: ResumeSaveRequest) -> ResumeResponse:
        current = self._get_resume(user_id)
        old_photo_id = _photo_id(current.content) if current else None
        new_photo_id = payload.content.basic_info.photo_id
        mime_type: str | None = None
        promoted = False
        if new_photo_id and new_photo_id != old_photo_id:
            mime_type = self._photo_storage.promote_staged(user_id, new_photo_id)
            promoted = True
        try:
            row = repository.save_resume(
                self._session,
                user_id,
                content=payload.content.model_dump(mode="json", exclude_none=True),
                style_config=payload.style_config.model_dump(mode="json"),
                expected_updated_at=payload.expected_updated_at,
            )
            if row is None:
                self._session.rollback()
                if promoted and new_photo_id:
                    self._best_effort_delete_photo(user_id, new_photo_id, mime_type)
                raise ResumeConflictError
            self._session.commit()
            result = self._to_response(row)
        except ResumeConflictError:
            raise
        except SQLAlchemyError:
            self._session.rollback()
            if promoted and new_photo_id:
                self._best_effort_delete_photo(user_id, new_photo_id, mime_type)
            raise ResumeConflictError from None
        if old_photo_id and old_photo_id != new_photo_id:
            self._best_effort_delete_photo(user_id, old_photo_id)
        if promoted and new_photo_id:
            self._best_effort_delete_staged(user_id, new_photo_id)
        return result

    def upload_photo(self, user_id: int, data: bytes) -> ResumePhotoUploadResponse:
        if not data or len(data) > MAX_PHOTO_BYTES:
            raise ResumePhotoError
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            mime_type = "image/png"
        elif data.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        else:
            raise ResumePhotoError
        photo_id = uuid.uuid4().hex
        self._photo_storage.upload_staged(user_id, photo_id, data, mime_type)
        return ResumePhotoUploadResponse(
            photo_id=photo_id, mime_type=mime_type, file_size=len(data)
        )

    def delete_staged_photo(self, user_id: int, photo_id: str) -> None:
        if not _PHOTO_ID_PATTERN.fullmatch(photo_id):
            raise ResumePhotoError
        current = self._get_resume(user_id)
        if current and _photo_id(current.content) == photo_id:
            raise ResumePhotoError
        self._photo_storage.delete_staged(user_id, photo_id)

    def get_saved_photo(self, user_id: int) -> tuple[bytes, str]:
        row = self._get_resume(user_id)
        photo_id = _photo_id(row.content) if row else None
        if not photo_id:
            raise ResumeNotFoundError
        return self._photo_storage.read_saved(user_id, photo_id)

    def export_pdf(self, user_id: int) -> bytes:
        row = self._get_resume(user_id)
        if row is None:
            raise ResumeNotFoundError
        content = ResumeContent.model_validate(row.content)
        style = ResumeStyleConfig.model_validate(row.style_config)
        photo_id = _photo_id(row.content)
        photo = self._photo_storage.read_saved(user_id, photo_id) if photo_id else None
        return self._pdf_renderer.render(content, style, photo=photo)

    def read_job_snapshot(self, user_id: int) -> JobResumeSnapshot:
        try:
            row = repository.get_resume(self._session, user_id)
            if row is None:
                return JobResumeSnapshot(status="not_found")
            content = ResumeContent.model_validate(row.content)
        except (SQLAlchemyError, ValidationError) as error:
            self._session.rollback()
            logger.warning("resume_agent_read_failed error_type=%s", type(error).__name__)
            return JobResumeSnapshot(status="unavailable")

        budget = _TextBudget()
        info = content.basic_info
        return JobResumeSnapshot(
            status="found",
            updated_at=row.updated_at,
            intended_position=budget.take(info.intended_position) or None,
            work_experience_years=info.work_experience_years,
            educations=[
                {
                    "school": budget.take(item.school),
                    "major": budget.take(item.major),
                    "degree": budget.take(item.degree),
                    "start_month": item.start_month,
                    "end_month": item.end_month,
                }
                for item in content.educations
            ],
            skills=budget.take(document_text(content.skills)),
            works=[
                {
                    "company": budget.take(item.company),
                    "position": budget.take(item.position),
                    "start_month": item.start_month,
                    "end_month": item.end_month,
                    "description": budget.take(document_text(item.content)),
                }
                for item in content.works
            ],
            projects=[
                {
                    "name": budget.take(item.name),
                    "role": budget.take(item.role),
                    "technology_stack": budget.take(item.technology_stack),
                    "start_month": item.start_month,
                    "end_month": item.end_month,
                    "description": budget.take(document_text(item.content)),
                }
                for item in content.projects
            ],
            truncated=budget.truncated,
        )

    def apply_optimization(self, user_id: int, candidate: dict[str, Any]) -> str:
        try:
            expected_updated_at = datetime.fromisoformat(candidate["source_updated_at"])
            scope = candidate["scope"]
            patch = candidate["patch"]
            if expected_updated_at.tzinfo is None or not isinstance(patch, dict):
                return "invalid_candidate"
            current = repository.get_resume(self._session, user_id)
            if current is None or current.updated_at != expected_updated_at:
                return "resume_changed"
            merged = deepcopy(ResumeContent.model_validate(current.content).model_dump(mode="json"))
            allowed = {
                "basic_info": {"basic_info"},
                "skills": {"skills"},
                "works": {"works"},
                "projects": {"projects"},
                "all": {"basic_info", "skills", "works", "projects"},
            }
            if scope not in allowed or set(patch) - allowed[scope]:
                return "invalid_candidate"
            for key, value in patch.items():
                if key == "basic_info":
                    if not isinstance(value, dict) or set(value) != {"intended_position"}:
                        return "invalid_candidate"
                    merged[key]["intended_position"] = value["intended_position"]
                elif key == "skills":
                    merged[key] = value
                elif key in {"works", "projects"}:
                    if not isinstance(value, list):
                        return "invalid_candidate"
                    seen: set[int] = set()
                    for change in value:
                        if not isinstance(change, dict) or set(change) != {"index", "content"}:
                            return "invalid_candidate"
                        index = change["index"]
                        if not isinstance(index, int) or isinstance(index, bool) or index in seen:
                            return "invalid_candidate"
                        if not 0 <= index < len(merged[key]):
                            return "invalid_candidate"
                        seen.add(index)
                        merged[key][index]["content"] = change["content"]
            validated = ResumeContent.model_validate(merged)
            if not repository.update_content_if_unchanged(
                self._session,
                user_id,
                expected_updated_at=expected_updated_at,
                content=validated.model_dump(mode="json", exclude_none=True),
            ):
                self._session.rollback()
                return "resume_changed"
            self._session.commit()
            return "saved"
        except (KeyError, TypeError, ValueError, ValidationError):
            self._session.rollback()
            return "invalid_candidate"
        except SQLAlchemyError as error:
            self._session.rollback()
            logger.warning("resume_agent_write_failed error_type=%s", type(error).__name__)
            return "unavailable"

    @staticmethod
    def _to_response(row: Any) -> ResumeResponse:
        return ResumeResponse(
            exists=True,
            content=ResumeContent.model_validate(row.content),
            style_config=ResumeStyleConfig.model_validate(row.style_config),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _get_resume(self, user_id: int) -> Resume | None:
        try:
            return repository.get_resume(self._session, user_id)
        except SQLAlchemyError as error:
            self._session.rollback()
            logger.warning("resume_read_failed error_type=%s", type(error).__name__)
            raise ResumeUnavailableError from None

    def _best_effort_delete_photo(
        self, user_id: int, photo_id: str, mime_type: str | None = None
    ) -> None:
        for photo_type in (mime_type,) if mime_type else ("image/png", "image/jpeg"):
            try:
                self._photo_storage.delete_saved(user_id, photo_id, photo_type)
            except ResumePhotoStorageError:
                logger.warning("resume_photo_cleanup_failed")

    def _best_effort_delete_staged(self, user_id: int, photo_id: str) -> None:
        try:
            self._photo_storage.delete_staged(user_id, photo_id)
        except ResumePhotoStorageError:
            logger.warning("resume_photo_cleanup_failed")


class _TextBudget:
    def __init__(self, limit: int = 12_000) -> None:
        self.remaining = limit
        self.truncated = False

    def take(self, value: str | None) -> str:
        text = (value or "").strip()
        result = text[: self.remaining]
        self.remaining -= len(result)
        self.truncated |= len(result) < len(text)
        return result


def _photo_id(content: dict[str, Any]) -> str | None:
    basic_info = content.get("basic_info")
    if not isinstance(basic_info, dict):
        return None
    photo_id = basic_info.get("photo_id")
    return photo_id if isinstance(photo_id, str) and _PHOTO_ID_PATTERN.fullmatch(photo_id) else None
