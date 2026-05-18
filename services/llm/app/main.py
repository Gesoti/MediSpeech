"""LLM microservice — BioGPT clinical text generation."""
from __future__ import annotations

import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import partial
from threading import Thread
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.tracing import create_trace, flush, init, tracing_status

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="biogpt")
_generator: Any = None
_device: str = "cpu"  # overwritten to "cuda" if available during _load_model
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _load_model() -> None:
    global _generator, _device
    if _generator is not None:
        return
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(settings.biogpt_model)
    model = AutoModelForCausalLM.from_pretrained(settings.biogpt_model).to(_device)
    _generator = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        device=0 if _device == "cuda" else -1,
    )


def _remove_repetition(text: str) -> str:
    sentences = _SENTENCE_SPLIT.split(text.strip())
    seen: set[str] = set()
    unique: list[str] = []
    for s in sentences:
        key = s.lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(s)
    return " ".join(unique)


def _generate_sync(prompt: str, max_new_tokens: int = 256) -> str:
    _load_model()
    if _generator is None:
        raise RuntimeError("BioGPT model failed to load; cannot generate text")

    results: list[dict[str, Any]] = _generator(
        prompt,
        max_new_tokens=max_new_tokens,
        num_beams=3,
        early_stopping=True,
        do_sample=False,
        repetition_penalty=1.3,
        no_repeat_ngram_size=3,
    )
    raw: str = results[0]["generated_text"]
    # The pipeline prepends the input prompt to the output
    if raw.startswith(prompt):
        raw = raw[len(prompt):]
    return _remove_repetition(raw.strip())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init(settings.langfuse_host, settings.langfuse_public_key, settings.langfuse_secret_key)
    loop = asyncio.get_running_loop()
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


@app.get("/health/tracing")
async def health_tracing() -> dict[str, Any]:
    return tracing_status()


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    trace = create_trace("llm-generate", input={"prompt_length": len(req.prompt)})
    t0 = time.perf_counter()

    loop = asyncio.get_running_loop()
    fn = partial(_generate_sync, req.prompt, req.max_length)
    text = await loop.run_in_executor(_executor, fn)

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


@app.post("/generate/stream")
async def generate_stream(req: GenerateRequest) -> StreamingResponse:
    """Stream BioGPT generation token-by-token via SSE."""
    if _generator is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    from transformers import TextIteratorStreamer

    streamer = TextIteratorStreamer(
        _generator.tokenizer,  # type: ignore[attr-defined]
        skip_prompt=True,
        skip_special_tokens=True,
    )

    generation_kwargs = dict(
        text_inputs=req.prompt,
        max_new_tokens=req.max_length,
        num_beams=1,  # beams > 1 incompatible with streaming
        do_sample=True,
        temperature=0.7,
        repetition_penalty=1.3,
        no_repeat_ngram_size=3,
        streamer=streamer,
    )

    thread = Thread(target=_generator, kwargs=generation_kwargs)  # type: ignore[arg-type]

    async def _event_stream() -> AsyncGenerator[str, None]:
        thread.start()
        loop = asyncio.get_running_loop()
        for token in streamer:
            if token:
                yield f"data: {token}\n\n"
            await loop.run_in_executor(None, lambda: None)  # yield control to event loop
        yield "data: [DONE]\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")
