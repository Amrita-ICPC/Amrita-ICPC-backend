import json
from typing import Optional
from uuid import UUID

from app.core.clients.redis import redis_client
from app.core.config import config
from app.core.logger import logger
from app.models.bank import Bank


class BankCache:
    """Cache handler for banks."""

    PREFIX = "bank"
    TTL = 3600  # 1 hour

    @classmethod
    def _get_key(cls, bank_id: UUID | str) -> str:
        return f"{config.PROJECT_NAME}:{cls.PREFIX}:{str(bank_id)}"

    @classmethod
    async def get_bank(cls, bank_id: UUID | str) -> Optional[dict]:
        """Get bank data from cache."""
        try:
            if not redis_client:
                return None
                
            key = cls._get_key(bank_id)
            data = await redis_client.get(key)
            
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Error getting bank from cache: {str(e)}")
            return None

    @classmethod
    async def set_bank(cls, bank: Bank) -> None:
        """Set bank data in cache."""
        try:
            if not redis_client:
                return

            key = cls._get_key(bank.id)
            
            # Convert bank logic to dict - basic fields
            # Note: We avoid caching large relation data (questions) deep in cache 
            # unless we specifically need them. For lightweight check, basic info is good.
            # But the requirement implies full details on GET. 
            # For now, sticking to basic info to avoid consistency hell with questions.
            data = {
                "id": str(bank.id),
                "name": bank.name,
                "description": bank.description,
                "created_by": str(bank.created_by),
                "is_public": False, # Future proofing
            }
            
            await redis_client.setex(key, cls.TTL, json.dumps(data))
        except Exception as e:
            logger.error(f"Error setting bank in cache: {str(e)}")

    @classmethod
    async def update_bank(cls, bank: Bank) -> None:
        """Update bank in cache."""
        await cls.set_bank(bank)

    @classmethod
    async def delete_bank(cls, bank_id: UUID | str) -> None:
        """Delete bank from cache."""
        try:
            if not redis_client:
                return

            key = cls._get_key(bank_id)
            await redis_client.delete(key)
        except Exception as e:
            logger.error(f"Error deleting bank from cache: {str(e)}")
