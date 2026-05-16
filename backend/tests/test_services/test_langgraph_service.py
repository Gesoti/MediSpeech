"""Unit tests for ClinicalWorkflow (LangGraph report pipeline)."""
import json

import pytest


@pytest.fixture
def mock_llm(monkeypatch):
    """Replace llm_service.generate with a deterministic stub."""
    from app.services import langgraph_service

    async def fake_generate(prompt: str, max_length: int = 512) -> str:
        return "Generated output for: " + prompt[:30]

    monkeypatch.setattr(langgraph_service.llm_service, "generate", fake_generate)


@pytest.fixture
def mock_llm_stream(monkeypatch):
    """Replace llm_service.generate_stream with a two-token async generator."""
    from app.services import langgraph_service

    async def fake_stream(prompt: str, max_length: int = 512):
        yield "Hello "
        yield "world "

    monkeypatch.setattr(langgraph_service.llm_service, "generate_stream", fake_stream)


@pytest.mark.asyncio
async def test_process_transcription_returns_all_sections(mock_llm) -> None:
    from app.services.langgraph_service import ClinicalWorkflow

    result = await ClinicalWorkflow().process_transcription(
        "5yo Labrador, hip pain for two weeks.",
        study_type="x-ray",
    )
    assert set(result.keys()) == {"clinical_history", "findings", "impressions", "recommendations"}
    for value in result.values():
        assert value is not None and len(value) > 0


@pytest.mark.asyncio
async def test_process_transcription_uses_study_type_prompt(monkeypatch) -> None:
    """Each study type injects its keyword into the history prompt."""
    from app.services import langgraph_service

    captured: list[str] = []

    async def capturing_generate(prompt: str, max_length: int = 512) -> str:
        captured.append(prompt)
        return "text"

    monkeypatch.setattr(langgraph_service.llm_service, "generate", capturing_generate)

    await langgraph_service.ClinicalWorkflow().process_transcription(
        "notes", study_type="ultrasound"
    )
    assert any("ULTRASOUND" in p.upper() for p in captured)


@pytest.mark.asyncio
async def test_process_transcription_unknown_type_uses_other(monkeypatch) -> None:
    """Unrecognised study type falls through to the 'other' template without raising."""
    from app.services import langgraph_service

    call_count = 0

    async def counting_generate(prompt: str, max_length: int = 512) -> str:
        nonlocal call_count
        call_count += 1
        return "text"

    monkeypatch.setattr(langgraph_service.llm_service, "generate", counting_generate)

    await langgraph_service.ClinicalWorkflow().process_transcription(
        "notes", study_type="fluoroscopy"  # not in templates
    )
    # All 4 pipeline steps must still execute
    assert call_count == 4


@pytest.mark.asyncio
async def test_process_transcription_propagates_llm_error(monkeypatch) -> None:
    from app.services import langgraph_service

    async def failing_generate(prompt: str, max_length: int = 512) -> str:
        raise RuntimeError("GPU OOM")

    monkeypatch.setattr(langgraph_service.llm_service, "generate", failing_generate)

    with pytest.raises(RuntimeError, match="GPU OOM"):
        await langgraph_service.ClinicalWorkflow().process_transcription(
            "notes", study_type="x-ray"
        )


@pytest.mark.asyncio
async def test_stream_report_yields_all_four_sections(mock_llm_stream) -> None:
    from app.services.langgraph_service import ClinicalWorkflow

    events: list[dict] = []
    async for raw in ClinicalWorkflow().stream_report("notes", study_type="x-ray"):
        events.append(json.loads(raw))

    sections = {e["section"] for e in events if "section" in e}
    assert sections == {"clinical_history", "findings", "impressions", "recommendations"}


@pytest.mark.asyncio
async def test_stream_report_final_event_is_complete(mock_llm_stream) -> None:
    from app.services.langgraph_service import ClinicalWorkflow

    events: list[dict] = []
    async for raw in ClinicalWorkflow().stream_report("notes", study_type="ultrasound"):
        events.append(json.loads(raw))

    final = next((e for e in events if e.get("status") == "complete"), None)
    assert final is not None
    assert "clinical_history" in final
    assert "findings" in final
    assert "impressions" in final
    assert "recommendations" in final


@pytest.mark.asyncio
async def test_stream_report_section_lifecycle(mock_llm_stream) -> None:
    """Each section must emit: start → ≥1 token → done, in that order."""
    from app.services.langgraph_service import ClinicalWorkflow

    events: list[dict] = []
    async for raw in ClinicalWorkflow().stream_report("notes", study_type="MRI"):
        events.append(json.loads(raw))

    for section in ("clinical_history", "findings", "impressions", "recommendations"):
        section_events = [e for e in events if e.get("section") == section]
        statuses = [e.get("status") for e in section_events]
        assert statuses[0] == "start"
        assert statuses[-1] == "done"
        # At least one token event between start and done
        token_events = [e for e in section_events if "token" in e]
        assert len(token_events) >= 1


@pytest.mark.asyncio
async def test_stream_impressions_uses_accumulated_history_and_findings(
    monkeypatch,
) -> None:
    """The impressions prompt must reference the text produced by history and findings steps."""
    from app.services import langgraph_service

    prompts_by_step: list[str] = []

    async def tracking_stream(prompt: str, max_length: int = 512):
        prompts_by_step.append(prompt)
        yield "output "

    monkeypatch.setattr(langgraph_service.llm_service, "generate_stream", tracking_stream)

    async for _ in langgraph_service.ClinicalWorkflow().stream_report(
        "notes", study_type="x-ray"
    ):
        pass

    # 4 prompts: history, findings, impressions, recommendations
    assert len(prompts_by_step) == 4
    impressions_prompt = prompts_by_step[2]
    # The accumulated text from steps 1 & 2 ("output") must appear in step 3's prompt
    assert "output" in impressions_prompt
