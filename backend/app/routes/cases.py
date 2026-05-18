"""Case CRUD routes."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.db import get_db
from app.models.case import Case
from app.schemas.case import CaseCreate, CaseResponse, CaseUpdate
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/cases", tags=["cases"])
logger = get_logger(__name__)


@router.post("", status_code=201)
async def create_case(
    case_data: CaseCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CaseResponse:
    """Create a new case for the authenticated user."""
    case = Case(
        user_id=user_id,
        pet_species=case_data.pet_species,
        pet_breed=case_data.pet_breed,
        study_type=case_data.study_type,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)

    logger.info(f"Case created: {case.id}")
    return CaseResponse.model_validate(case)


@router.get("")
async def list_cases(
    db: AsyncSession = Depends(get_db),
) -> list[CaseResponse]:
    """List all cases (for demo; later filter by user)."""
    result = await db.execute(select(Case))
    cases = result.scalars().all()
    return [CaseResponse.model_validate(c) for c in cases]


@router.get("/{case_id}")
async def get_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CaseResponse:
    """Get a specific case."""
    result = await db.execute(select(Case).filter(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseResponse.model_validate(case)


@router.patch("/{case_id}")
async def update_case(
    case_id: UUID,
    case_data: CaseUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CaseResponse:
    """Update a case."""
    result = await db.execute(select(Case).filter(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if case_data.pet_species:
        case.pet_species = case_data.pet_species
    if case_data.pet_breed:
        case.pet_breed = case_data.pet_breed
    if case_data.study_type:
        case.study_type = case_data.study_type

    await db.commit()
    await db.refresh(case)
    return CaseResponse.model_validate(case)


@router.delete("/{case_id}")
async def delete_case(
    case_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a case (cascades to audio, transcriptions, reports)."""
    result = await db.execute(select(Case).filter(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await db.delete(case)
    await db.commit()
    return {"message": "Case deleted"}
