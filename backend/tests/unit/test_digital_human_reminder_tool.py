from types import SimpleNamespace

from app.modules.digital_human.agent.tools import reminder


def test_tool_creates_for_authenticated_user(monkeypatch):
    user = SimpleNamespace(id=42, is_guest=False)
    calls = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, model, user_id):
            assert user_id == 42
            return user

    class Access:
        def __init__(self, *args):
            pass

        def require_member(self, user_id, *, is_guest):
            assert (user_id, is_guest) == (42, False)

    class Service:
        def __init__(self, session):
            pass

        def create(self, current_user, payload):
            from datetime import UTC, datetime

            calls.append((current_user, payload))
            return SimpleNamespace(
                id="1",
                title=payload.title,
                repeat_type="once",
                timezone=payload.timezone,
                next_run_at=datetime(2030, 1, 1, tzinfo=UTC),
            )

    monkeypatch.setattr(reminder, "SessionLocal", Session)
    monkeypatch.setattr(
        reminder, "create_redis_client", lambda: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(reminder, "MembershipAccessService", Access)
    monkeypatch.setattr(reminder, "ReminderService", Service)
    result = reminder.create_reminder.invoke(
        {
            "title": "周报",
            "content": "提交周报",
            "repeat_type": "once",
            "date": "2030-01-01",
            "local_time": "09:00",
            "timezone": "Asia/Shanghai",
        },
        config={"configurable": {"user_id": 42}},
    )
    assert "提醒已创建" in result
    assert len(calls) == 1 and calls[0][0] is user
