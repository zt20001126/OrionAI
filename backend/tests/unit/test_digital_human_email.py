"""验证邮件确认与 SMTP 发送之间的业务边界。"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.agent.schemas import QuestionPayload
from app.modules.conversations.service.service import ConversationService
from app.modules.digital_human.agent.runtime import DigitalHumanRuntime
from app.modules.digital_human.agent.tools import email
from tests.unit.test_digital_human_agent import ScriptedChatModel


class MemoryRedis:
    """模拟草稿原子领取，供邮件流程测试使用。"""

    def __init__(self):
        self.values = {}

    def set(self, key, value, ex):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def getdel(self, key):
        return self.values.pop(key, None)

    def close(self):
        pass


@pytest.mark.anyio
async def test_email_confirmation_sends_once(monkeypatch):
    """题卡展示草稿，确认后仅能发送一次，正文保留用户联系邮箱。"""
    store = MemoryRedis()
    settings = SimpleNamespace(smtp_from_email="platform@example.com")
    monkeypatch.setattr(email, "create_redis_client", lambda: store)
    monkeypatch.setattr(email, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.modules.conversations.service.service.create_redis_client", lambda: store
    )
    monkeypatch.setattr("app.modules.conversations.service.service.get_settings", lambda: settings)
    sent = []
    monkeypatch.setattr(
        "app.modules.conversations.service.service.send_email", lambda *a, **kw: sent.append(kw)
    )
    call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "prepare_email",
                "args": {
                    "recipient": "to@example.com",
                    "subject": "你好",
                    "body": "联系我：me@example.com",
                },
                "id": "email-call",
                "type": "tool_call",
            }
        ],
    )
    runtime = DigitalHumanRuntime(chat_model=ScriptedChatModel([call]))
    result = await runtime.ainvoke(
        "发送邮件", runnable_config={"configurable": {"user_id": 1, "conversation_id": 2}}
    )
    assert result.status == "waiting"
    question = result.questions.questions[0]
    assert "platform@example.com" in question.context
    assert "me@example.com" in question.context
    result_text = ConversationService._process_email_confirmation(1, 2, question, "确认发送")
    assert "已接受" in result_text
    assert sent == [
        {"recipient": "to@example.com", "subject": "你好", "text_body": "联系我：me@example.com"}
    ]
    assert "已失效" in ConversationService._process_email_confirmation(1, 2, question, "确认发送")
    assert len(sent) == 1


def test_invalid_recipient_rejected():
    """工具边界拒绝邮件头注入和无效地址。"""
    with pytest.raises(ValueError):
        email.EmailDraftInput(
            recipient="x@example.com\nBcc: a@example.com", subject="标题", body="正文"
        )


def test_cancel_and_altered_preview_do_not_send(monkeypatch):
    """取消或篡改预览不能触发发信，草稿不得跨用户使用。"""
    from app.modules.conversations.errors.errors import ConversationValidationError

    store = MemoryRedis()
    settings = SimpleNamespace(smtp_from_email="platform@example.com")
    monkeypatch.setattr(email, "create_redis_client", lambda: store)
    monkeypatch.setattr(email, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.modules.conversations.service.service.create_redis_client", lambda: store
    )
    monkeypatch.setattr("app.modules.conversations.service.service.get_settings", lambda: settings)
    sent = []
    monkeypatch.setattr(
        "app.modules.conversations.service.service.send_email",
        lambda *args, **kwargs: sent.append(kwargs),
    )
    raw = email.prepare_email.invoke(
        {"recipient": "to@example.com", "subject": "标题", "body": "正文"},
        config={"configurable": {"user_id": 1, "conversation_id": 2}},
    )
    question = QuestionPayload.model_validate_json(raw).questions[0]
    changed = question.model_copy(update={"context": "篡改内容"})
    with pytest.raises(ConversationValidationError):
        ConversationService._process_email_confirmation(1, 2, changed, "确认发送")
    assert "失效" in ConversationService._process_email_confirmation(3, 2, question, "确认发送")
    assert "取消" in ConversationService._process_email_confirmation(1, 2, question, "取消发送")
    assert not sent
