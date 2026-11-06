"""验证数字人视频任务编排与私有结果读取。"""

from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.modules.digital_human.providers.video.bailian import BailianVideoClient
from app.modules.digital_human.service import video_generation


@pytest.mark.anyio
async def test_generate_video_polls_once_and_saves_to_oss(monkeypatch):
    """百炼任务完成后保存 MP4，保留任务标识并更新成功状态。"""
    statuses = []
    submissions = []

    class Store:
        def create_running(self, **kwargs):
            statuses.append(("created", kwargs))

        def set_status(self, task_id, **kwargs):
            statuses.append((task_id, kwargs))

    class Client:
        def __init__(self, settings):
            pass

        async def submit(self, prompt):
            submissions.append(prompt)
            return "provider-123"

        async def get_task(self, task_id):
            assert task_id == "provider-123"
            return {"task_status": "SUCCEEDED", "video_url": "https://example.test/v.mp4"}

        async def download(self, url):
            return b"video bytes"

    class Storage:
        def __init__(self, settings):
            pass

        def put_object(self, key, data, **kwargs):
            assert data == b"video bytes"
            assert kwargs["content_type"] == "video/mp4"
            return SimpleNamespace(key=key)

    monkeypatch.setattr(video_generation, "TaskResultStore", Store)
    monkeypatch.setattr(video_generation, "BailianVideoClient", Client)
    monkeypatch.setattr(video_generation, "AliyunOSSObjectStorage", Storage)
    monkeypatch.setattr(video_generation, "generate_snowflake_id", lambda: 123)
    result = await video_generation.generate_and_save_video(
        settings=SimpleNamespace(), user_id=1, conversation_id=2, prompt="小猫跑步"
    )
    assert result == "123"
    assert submissions == ["小猫跑步"]
    assert statuses[-1][1] == {
        "status": "succeeded",
        "result_data": {"provider_task_id": "provider-123", "object_key": "videos/1/2/123.mp4"},
    }


def test_video_result_rejects_other_user(monkeypatch):
    """无法按当前用户查到的任务不能读取 OSS。"""
    monkeypatch.setattr(video_generation.repository, "get_user_task_result", lambda *args: None)
    with pytest.raises(video_generation.VideoResultUnavailableError):
        video_generation.get_user_video(SimpleNamespace(), 10, 123)


@pytest.mark.anyio
async def test_failed_video_task_does_not_upload(monkeypatch):
    """百炼报告失败时，保留上游任务 ID 并把本地任务标记为失败。"""
    states = []

    class Store:
        def create_running(self, **kwargs):
            pass

        def set_status(self, task_id, **kwargs):
            states.append(kwargs)

    class Client:
        def __init__(self, settings):
            pass

        async def submit(self, prompt):
            return "provider-123"

        async def get_task(self, task_id):
            return {"task_status": "FAILED"}

    monkeypatch.setattr(video_generation, "TaskResultStore", Store)
    monkeypatch.setattr(video_generation, "BailianVideoClient", Client)
    monkeypatch.setattr(video_generation, "generate_snowflake_id", lambda: 123)
    with pytest.raises(ValueError, match="视频生成任务失败"):
        await video_generation.generate_and_save_video(
            settings=SimpleNamespace(), user_id=1, conversation_id=2, prompt="小猫跑步"
        )
    assert states == [
        {"status": "running", "result_data": {"provider_task_id": "provider-123"}},
        {"status": "failed"},
    ]


@pytest.mark.anyio
async def test_bailian_video_submit_and_query(monkeypatch):
    """视频请求使用异步接口，后续通过同一任务 ID 查询。"""
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"output": {"task_id": "task-123"}})
        return httpx.Response(200, json={"output": {"task_status": "SUCCEEDED"}})

    transport = httpx.MockTransport(respond)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: async_client(transport=transport, **kwargs)
    )
    settings = Settings(
        aliyun_bailian_api_key="test-key",
        aliyun_bailian_base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    client = BailianVideoClient(settings)
    task_id = await client.submit("小猫跑步")
    result = await client.get_task(task_id)
    assert task_id == "task-123"
    assert result["task_status"] == "SUCCEEDED"
    assert requests[0].headers["x-dashscope-async"] == "enable"
    assert requests[0].url.path == "/api/v1/services/aigc/video-generation/video-synthesis"
    assert requests[1].url.path == "/api/v1/tasks/task-123"
