import json
from datetime import datetime, timezone

from redis.asyncio.client import Redis

from app.schema.student.workspace import WorkspaceData


class WorkspaceService:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    async def save_workspace(
        self,
        key: str,
        language_id: int,
        source_code: str,
    ) -> None:
        payload = {
            "language_id": language_id,
            "source_code": source_code,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        await self.redis.set(
            key,
            json.dumps(payload),
            ex=60 * 60 * 24 * 7,  # 7 days
        )

    async def get_workspace(
        self,
        key: str,
    ) -> WorkspaceData | None:
        data = await self.redis.get(key)

        if data is None:
            return None

        return WorkspaceData.model_validate(json.loads(data))
