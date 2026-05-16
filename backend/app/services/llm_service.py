"""Medical LLM service — delegates to the LLM microservice over HTTP."""
import asyncio
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MedicalLLMService:
    """Calls the standalone LLM microservice for clinical text generation."""

    async def generate(self, prompt: str, max_length: int = 512) -> str:
        logger.info(f"Sending generation request (max_length={max_length})")
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{settings.llm_service_url}/generate",
                json={"prompt": prompt, "max_length": max_length},
            )
            response.raise_for_status()
        result: str = response.json()["text"]
        logger.info(f"LLM response received: {len(result)} chars")
        return result

    async def generate_stream(
        self, prompt: str, max_length: int = 512
    ) -> AsyncIterator[str]:
        """Fetch the full response then stream it word-by-word for SSE compatibility."""
        full_text = await self.generate(prompt, max_length)
        for word in full_text.split():
            yield word + " "
            await asyncio.sleep(0)


llm_service = MedicalLLMService()
