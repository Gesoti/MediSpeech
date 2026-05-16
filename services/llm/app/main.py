"""LLM microservice — BioGPT clinical text generation."""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import settings
from app.tracing import create_trace, flush

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="biogpt")
_tokenizer: Any = None
_model: Any = None
_device: str = "cpu"


def _load_model() -> None:
    global _tokenizer, _model, _device
    if _model is not None:
        return
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _tokenizer = AutoTokenizer.from_pretrained(settings.biogpt_model)
    _model = AutoModelForCausalLM.from_pretrained(settings.biogpt_model).to(_device)


def _generate_sync(prompt: str) -> str:
    _load_model()
    import torch

    assert _tokenizer is not None
    assert _model is not None

    inputs = _tokenizer.encode(prompt, return_tensors="pt").to(_device)
    with torch.no_grad():
        outputs = _model.generate(
            inputs,
            num_beams=3,
            early_stopping=True,
            temperature=0.7,
        )
    result: str = _tokenizer.decode(outputs[0], skip_special_tokens=True)
    if result.startswith(prompt):
        result = result[len(prompt):]
    return result.strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _load_model)
    yield
    flush()


app = FastAPI(title="MediSpeech LLM Service", lifespan=lifespan)


class GenerateRequest(BaseModel):
    prompt: str
    max_length: int = 512


class GenerateResponse(BaseModel):
    text: str
    model: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "llm"}


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    trace = create_trace("llm-generate", input={"prompt_length": len(req.prompt)})
    t0 = time.perf_counter()

    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(_executor, _generate_sync, req.prompt)

    elapsed = time.perf_counter() - t0
    if trace is not None:
        try:
            trace.generation(
                name="biogpt",
                model=settings.biogpt_model,
                input=req.prompt,
                output=text,
                usage={"completion_tokens": len(text.split())},
                metadata={"elapsed_seconds": round(elapsed, 2)},
            ).end()
        except Exception:
            pass

    return GenerateResponse(text=text, model=settings.biogpt_model)
