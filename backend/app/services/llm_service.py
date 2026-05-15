"""Medical LLM service for clinical text generation."""
import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

from app.utils.logger import get_logger

logger = get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="llm-worker")


class MedicalLLMService:
    """Service for medical language model inference."""

    def __init__(self) -> None:
        """Initialize medical LLM service (lazy loads model on first use)."""
        self.tokenizer = None
        self.model = None
        self.device = None
        self._initialized = False

    def _ensure_loaded(self) -> None:
        """Ensure model is loaded before use."""
        if self._initialized:
            return

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model_name = "microsoft/BioGPT"
            device = "cpu"

            logger.info(f"Loading {model_name}...")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForCausalLM.from_pretrained(model_name).to(device)
            self.device = device
            self._initialized = True
            logger.info(f"Model loaded on {device}")
        except Exception as e:
            logger.error(f"Failed to load LLM: {str(e)}")
            raise

    def _generate_sync(self, prompt: str, max_length: int = 512) -> str:
        """Synchronous generation — runs in thread pool."""
        try:
            self._ensure_loaded()

            import torch

            assert self.tokenizer is not None
            assert self.model is not None
            assert self.device is not None

            inputs = self.tokenizer.encode(prompt, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs,
                    max_length=max_length,
                    num_beams=3,
                    early_stopping=True,
                    temperature=0.7,
                )
            result: str = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            # Strip the prompt prefix that BioGPT echoes back
            if result.startswith(prompt):
                result = result[len(prompt):]
            return result.strip()
        except Exception as e:
            logger.error(f"Generation error: {str(e)}")
            raise

    async def generate(self, prompt: str, max_length: int = 512) -> str:
        """Generate medical text from prompt (non-blocking)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._generate_sync, prompt, max_length)

    async def generate_stream(self, prompt: str, max_length: int = 512) -> AsyncIterator[str]:
        """Stream generated tokens one by one (simulated via thread pool).

        BioGPT does not natively support token streaming, so we generate the full
        response in a thread and yield words progressively to keep the SSE contract.
        """
        full_text = await self.generate(prompt, max_length)
        for word in full_text.split():
            yield word + " "
            await asyncio.sleep(0)  # yield control between words


llm_service = MedicalLLMService()
