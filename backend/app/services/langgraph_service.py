"""Clinical reasoning workflow — async pipeline with Langfuse tracing."""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from typing_extensions import TypedDict

from app.services.llm_service import llm_service
from app.utils.logger import get_logger
from app.utils.tracing import create_trace

logger = get_logger(__name__)


class ClinicalState(TypedDict):
    """Accumulated state for the clinical analysis workflow."""

    transcription: str
    study_type: str
    clinical_history: str | None
    findings: str | None
    impressions: str | None
    recommendations: str | None
    error: str | None


# ---------------------------------------------------------------------------
# Study-type-specific prompt templates
# ---------------------------------------------------------------------------

_HISTORY_PROMPTS: dict[str, str] = {
    "x-ray": (
        "From the following veterinary radiologist's spoken notes for an X-RAY study, "
        "extract and structure the clinical history. Include: "
        "(1) Signalment (species, breed, age, sex/neuter status), "
        "(2) Presenting complaint and duration, "
        "(3) Relevant prior imaging or diagnostics, "
        "(4) Clinical indication for radiographic examination, "
        "(5) Number and type of views requested.\n\n"
        "Notes: {transcription}\n\nClinical History:"
    ),
    "ultrasound": (
        "From the following veterinary radiologist's spoken notes for an ULTRASOUND study, "
        "extract and structure the clinical history. Include: "
        "(1) Signalment (species, breed, age, sex/neuter status), "
        "(2) Presenting complaint and duration, "
        "(3) Relevant prior diagnostics or bloodwork, "
        "(4) Clinical indication for sonographic examination, "
        "(5) Body region(s) to be assessed.\n\n"
        "Notes: {transcription}\n\nClinical History:"
    ),
    "MRI": (
        "From the following veterinary radiologist's spoken notes for an MRI study, "
        "extract and structure the clinical history. Include: "
        "(1) Signalment (species, breed, age, sex/neuter status), "
        "(2) Neurological or orthopaedic presenting signs, "
        "(3) Duration and progression of signs, "
        "(4) Prior treatments and response, "
        "(5) Clinical indication and anatomic region of interest, "
        "(6) Whether gadolinium contrast was administered.\n\n"
        "Notes: {transcription}\n\nClinical History:"
    ),
    "CT scan": (
        "From the following veterinary radiologist's spoken notes for a CT SCAN study, "
        "extract and structure the clinical history. Include: "
        "(1) Signalment (species, breed, age, sex/neuter status), "
        "(2) Presenting complaint and duration, "
        "(3) Relevant prior imaging or laboratory data, "
        "(4) Clinical indication for CT examination, "
        "(5) Scan region(s) and whether contrast was planned.\n\n"
        "Notes: {transcription}\n\nClinical History:"
    ),
    "other": (
        "From the following veterinary radiologist's spoken notes, extract and structure "
        "the clinical history. Include: "
        "(1) Signalment (species, breed, age, sex/neuter status), "
        "(2) Presenting complaint, "
        "(3) Clinical indication for imaging.\n\n"
        "Notes: {transcription}\n\nClinical History:"
    ),
}

_FINDINGS_PROMPTS: dict[str, str] = {
    "x-ray": (
        "Based on the following radiological notes for an X-RAY study, provide structured findings "
        "using radiographic Roentgen signs (size, shape, opacity, number, position, margins). "
        "Organise findings under these headings where applicable: "
        "VIEWS OBTAINED | IMAGE QUALITY | SKELETAL STRUCTURES | SOFT TISSUE SILHOUETTES | "
        "GASTROINTESTINAL TRACT | URINARY TRACT | THORACIC STRUCTURES | INCIDENTAL FINDINGS.\n\n"
        "Notes: {transcription}\n\nRadiographic Findings:"
    ),
    "ultrasound": (
        "Based on the following notes for an ULTRASOUND study, provide structured sonographic findings. "
        "Organise under organ headings and document echogenicity, size with measurements, border "
        "characteristics, and any masses (with dimensions). Include: "
        "LIVER & GALLBLADDER | SPLEEN | PANCREAS | KIDNEYS (with length/cortical measurements) | "
        "ADRENAL GLANDS | URINARY BLADDER | GI TRACT | PERITONEAL CAVITY | LYMPH NODES | "
        "DOPPLER FINDINGS (if applicable).\n\n"
        "Notes: {transcription}\n\nSonographic Findings:"
    ),
    "MRI": (
        "Based on the following notes for an MRI study, provide structured MRI findings. "
        "Organise under these headings: "
        "SEQUENCES ACQUIRED | ANATOMIC REGION | SIGNAL INTENSITY (T1/T2/FLAIR/DWI) | "
        "CONTRAST ENHANCEMENT PATTERN | FOCAL LESIONS (dimensions, margins, mass effect) | "
        "VASCULAR STRUCTURES | INCIDENTAL FINDINGS. "
        "Use standard MRI signal terminology (hyperintense/hypointense/isointense).\n\n"
        "Notes: {transcription}\n\nMRI Findings:"
    ),
    "CT scan": (
        "Based on the following notes for a CT SCAN study, provide structured CT findings. "
        "Organise under these headings: "
        "SCAN PROTOCOL (pre/post contrast, slice thickness) | BONE WINDOW FINDINGS | "
        "SOFT TISSUE WINDOW FINDINGS (HU values where stated) | VASCULAR STRUCTURES | "
        "LYMPH NODES (short-axis measurements) | PERITONEAL/PLEURAL SPACES | "
        "3D MEASUREMENTS OF LESIONS | INCIDENTAL FINDINGS. "
        "Use standard CT density terminology (hypodense/isodense/hyperdense).\n\n"
        "Notes: {transcription}\n\nCT Findings:"
    ),
    "other": (
        "Based on the following radiological notes, provide structured findings describing "
        "all relevant imaging observations systematically by anatomic region.\n\n"
        "Notes: {transcription}\n\nFindings:"
    ),
}

_IMPRESSIONS_PROMPTS: dict[str, str] = {
    "x-ray": (
        "Based on the clinical history and radiographic findings below, provide a numbered "
        "list of radiographic diagnoses or differential diagnoses in order of likelihood. "
        "Use explicit confidence language (e.g. 'consistent with', 'compatible with', "
        "'cannot exclude'). Reference specific Roentgen sign deviations.\n\n"
        "Clinical History: {clinical_history}\nFindings: {findings}\n\nRadiographic Impression:"
    ),
    "ultrasound": (
        "Based on the clinical history and sonographic findings below, provide a numbered "
        "list of sonographic diagnoses or differential diagnoses in order of likelihood. "
        "Use explicit confidence language. Reference organ measurements relative to "
        "normal reference ranges where relevant.\n\n"
        "Clinical History: {clinical_history}\nFindings: {findings}\n\nSonographic Impression:"
    ),
    "MRI": (
        "Based on the clinical history and MRI findings below, provide a numbered list of "
        "diagnoses or differential diagnoses with anatomical localisation and severity grading. "
        "Use explicit confidence language. Note signal characteristics supporting each diagnosis.\n\n"
        "Clinical History: {clinical_history}\nFindings: {findings}\n\nMRI Impression:"
    ),
    "CT scan": (
        "Based on the clinical history and CT findings below, provide a numbered list of "
        "diagnoses or differential diagnoses. Include staging or severity classification "
        "where appropriate. Note HU values or enhancement patterns supporting each diagnosis.\n\n"
        "Clinical History: {clinical_history}\nFindings: {findings}\n\nCT Impression:"
    ),
    "other": (
        "Based on the clinical history and imaging findings below, provide a numbered list "
        "of diagnoses or differential diagnoses in order of likelihood.\n\n"
        "Clinical History: {clinical_history}\nFindings: {findings}\n\nImpression:"
    ),
}

_RECOMMENDATIONS_PROMPTS: dict[str, str] = {
    "x-ray": (
        "Based on the radiographic impression and findings below, provide numbered "
        "recommendations. Consider: additional radiographic views, orthogonal projections, "
        "cross-sectional imaging upgrade (CT/MRI), follow-up interval, and correlation "
        "with clinical examination or laboratory data.\n\n"
        "Findings: {findings}\nImpression: {impressions}\n\nRecommendations:"
    ),
    "ultrasound": (
        "Based on the sonographic impression and findings below, provide numbered "
        "recommendations. Consider: repeat sonography interval, cross-sectional imaging "
        "(CT/MRI), fine needle aspirate or biopsy guidance, urinalysis, "
        "clinicopathological correlation, and specialist referral.\n\n"
        "Findings: {findings}\nImpression: {impressions}\n\nRecommendations:"
    ),
    "MRI": (
        "Based on the MRI impression and findings below, provide numbered recommendations. "
        "Consider: surgical or medical management, contrast-enhanced follow-up MRI interval, "
        "CSF analysis, electrodiagnostics, specialist referral (neurology/orthopaedics), "
        "and prognosis correlation.\n\n"
        "Findings: {findings}\nImpression: {impressions}\n\nRecommendations:"
    ),
    "CT scan": (
        "Based on the CT impression and findings below, provide numbered recommendations. "
        "Consider: surgical planning, oncological staging workup, CT-guided biopsy, "
        "follow-up CT interval, additional imaging modalities, and specialist referral.\n\n"
        "Findings: {findings}\nImpression: {impressions}\n\nRecommendations:"
    ),
    "other": (
        "Based on the imaging impression and findings below, provide numbered recommendations "
        "for follow-up care, further diagnostics, and clinical management.\n\n"
        "Findings: {findings}\nImpression: {impressions}\n\nRecommendations:"
    ),
}


def _get_prompt(templates: dict[str, str], study_type: str, **kwargs: str) -> str:
    template = templates.get(study_type, templates["other"])
    return template.format(**kwargs)


# ---------------------------------------------------------------------------
# Async workflow
# ---------------------------------------------------------------------------


class ClinicalWorkflow:
    """Async clinical reasoning workflow."""

    async def _run_step(
        self,
        trace: Any,
        step_name: str,
        prompt: str,
        max_length: int = 512,
    ) -> str:
        t0 = time.perf_counter()
        span = None
        if trace is not None:
            try:
                span = trace.generation(
                    name=step_name,
                    input=prompt,
                    model="biogpt",
                )
            except Exception:
                pass

        result = await llm_service.generate(prompt, max_length)

        if span is not None:
            try:
                span.end(output=result, usage={"completion_tokens": len(result.split())})
            except Exception:
                pass

        elapsed = time.perf_counter() - t0
        logger.info(f"{step_name}: {len(result)} chars in {elapsed:.2f}s")
        return result

    async def process_transcription(
        self, transcription: str, study_type: str = "other", trace_id: str | None = None
    ) -> dict[str, str | None]:
        """Run all 4 generation steps and return the completed state."""
        trace = create_trace(
            "report-generation",
            input={"study_type": study_type, "transcription_length": len(transcription)},
            **({"id": trace_id} if trace_id else {}),
        )

        try:
            clinical_history = await self._run_step(
                trace,
                "extract_history",
                _get_prompt(_HISTORY_PROMPTS, study_type, transcription=transcription),
                max_length=256,
            )

            findings = await self._run_step(
                trace,
                "generate_findings",
                _get_prompt(_FINDINGS_PROMPTS, study_type, transcription=transcription),
                max_length=512,
            )

            impressions = await self._run_step(
                trace,
                "generate_impressions",
                _get_prompt(
                    _IMPRESSIONS_PROMPTS,
                    study_type,
                    clinical_history=clinical_history,
                    findings=findings,
                ),
                max_length=512,
            )

            recommendations = await self._run_step(
                trace,
                "generate_recommendations",
                _get_prompt(
                    _RECOMMENDATIONS_PROMPTS,
                    study_type,
                    findings=findings,
                    impressions=impressions,
                ),
                max_length=256,
            )

            if trace is not None:
                try:
                    trace.update(output={"status": "completed"})
                except Exception:
                    pass

            return {
                "clinical_history": clinical_history,
                "findings": findings,
                "impressions": impressions,
                "recommendations": recommendations,
            }
        except Exception as exc:
            if trace is not None:
                try:
                    trace.update(level="ERROR", status_message=str(exc))
                except Exception:
                    pass
            logger.error(f"Workflow error: {exc}")
            raise

    async def stream_report(
        self, transcription: str, study_type: str = "other", trace_id: str | None = None
    ) -> AsyncIterator[str]:
        """Stream the report section by section as Server-Sent Events data lines.

        Each yielded string is a JSON-serialisable SSE data payload.
        """
        import json

        trace = create_trace(
            "report-generation-stream",
            input={"study_type": study_type, "transcription_length": len(transcription)},
            **({"id": trace_id} if trace_id else {}),
        )

        sections: list[tuple[str, dict[str, str], str, int]] = [
            (
                "clinical_history",
                _HISTORY_PROMPTS,
                "extract_history",
                256,
            ),
        ]

        accumulated: dict[str, str] = {}

        # 1. History
        yield json.dumps({"section": "clinical_history", "status": "start"})
        history_prompt = _get_prompt(_HISTORY_PROMPTS, study_type, transcription=transcription)
        history_text = ""
        async for token in llm_service.generate_stream(history_prompt, 256):
            history_text += token
            yield json.dumps({"section": "clinical_history", "token": token})
        accumulated["clinical_history"] = history_text.strip()
        yield json.dumps({"section": "clinical_history", "status": "done", "text": accumulated["clinical_history"]})

        # 2. Findings
        yield json.dumps({"section": "findings", "status": "start"})
        findings_prompt = _get_prompt(_FINDINGS_PROMPTS, study_type, transcription=transcription)
        findings_text = ""
        async for token in llm_service.generate_stream(findings_prompt, 512):
            findings_text += token
            yield json.dumps({"section": "findings", "token": token})
        accumulated["findings"] = findings_text.strip()
        yield json.dumps({"section": "findings", "status": "done", "text": accumulated["findings"]})

        # 3. Impressions (depends on history + findings)
        yield json.dumps({"section": "impressions", "status": "start"})
        impressions_prompt = _get_prompt(
            _IMPRESSIONS_PROMPTS,
            study_type,
            clinical_history=accumulated["clinical_history"],
            findings=accumulated["findings"],
        )
        impressions_text = ""
        async for token in llm_service.generate_stream(impressions_prompt, 512):
            impressions_text += token
            yield json.dumps({"section": "impressions", "token": token})
        accumulated["impressions"] = impressions_text.strip()
        yield json.dumps({"section": "impressions", "status": "done", "text": accumulated["impressions"]})

        # 4. Recommendations (depends on findings + impressions)
        yield json.dumps({"section": "recommendations", "status": "start"})
        rec_prompt = _get_prompt(
            _RECOMMENDATIONS_PROMPTS,
            study_type,
            findings=accumulated["findings"],
            impressions=accumulated["impressions"],
        )
        rec_text = ""
        async for token in llm_service.generate_stream(rec_prompt, 256):
            rec_text += token
            yield json.dumps({"section": "recommendations", "token": token})
        accumulated["recommendations"] = rec_text.strip()
        yield json.dumps({"section": "recommendations", "status": "done", "text": accumulated["recommendations"]})

        yield json.dumps({"status": "complete", **accumulated})

        if trace is not None:
            try:
                trace.update(output={"status": "streamed"})
            except Exception:
                pass


clinical_workflow = ClinicalWorkflow()
