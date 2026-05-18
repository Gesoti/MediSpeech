"""Medical LLM service — delegates to the LLM microservice over HTTP."""
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
        """Stream tokens from the LLM service via SSE."""
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{settings.llm_service_url}/generate/stream",
                json={"prompt": prompt, "max_length": max_length},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        token = line[6:]
                        if token == "[DONE]":
                            return
                        if token:
                            yield token


llm_service = MedicalLLMService()
