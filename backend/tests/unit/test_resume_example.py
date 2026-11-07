"""验证未保存简历的示例内容和已有简历的读取边界。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.resume import repository
from app.modules.resume.schemas import ResumeSaveRequest, document_text
from app.modules.resume.service import ResumeApplicationService


def test_unsaved_resume_returns_complete_saveable_example_without_writing() -> None:
    session = MagicMock()
    service = ResumeApplicationService(session, photo_storage=MagicMock())
    service._get_resume = MagicMock(return_value=None)

    result = service.get_resume(123)

    assert result.exists is False
    assert result.updated_at is None
    assert result.content.basic_info.intended_position == "算法工程师"
    assert result.content.educations
    assert document_text(result.content.skills)
    assert result.content.works and document_text(result.content.works[0].content)
    assert result.content.projects and document_text(result.content.projects[0].content)
    ResumeSaveRequest(content=result.content, style_config=result.style_config)
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_saved_resume_is_returned_without_replacing_its_content() -> None:
    service = ResumeApplicationService(MagicMock(), photo_storage=MagicMock())
    service._get_resume = MagicMock(return_value=None)
    saved = service.get_resume(123)
    saved.content.basic_info.name = "用户姓名"
    timestamp = datetime.now(UTC)
    service._get_resume.return_value = SimpleNamespace(
        content=saved.content.model_dump(mode="json"),
        style_config=saved.style_config.model_dump(mode="json"),
        created_at=timestamp,
        updated_at=timestamp,
    )

    result = service.get_resume(123)

    assert result.exists is True
    assert result.content.basic_info.name == "用户姓名"
    assert result.updated_at == timestamp


def test_example_can_be_saved(monkeypatch) -> None:
    session = MagicMock()
    service = ResumeApplicationService(session, photo_storage=MagicMock())
    service._get_resume = MagicMock(return_value=None)
    example = service.get_resume(123)
    timestamp = datetime.now(UTC)
    saved_row = SimpleNamespace(
        content=example.content.model_dump(mode="json"),
        style_config=example.style_config.model_dump(mode="json"),
        created_at=timestamp,
        updated_at=timestamp,
    )
    save = MagicMock(return_value=saved_row)
    monkeypatch.setattr(repository, "save_resume", save)

    result = service.save_resume(
        123, ResumeSaveRequest(content=example.content, style_config=example.style_config)
    )

    assert result.exists is True
    assert result.content == example.content
    assert save.call_args.kwargs["expected_updated_at"] is None
    session.commit.assert_called_once()
