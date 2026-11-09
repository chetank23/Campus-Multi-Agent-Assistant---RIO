"""
backend/routes/settings.py
--------------------------
API routes for Admin Settings and Safe Operational Data Management.
Mounted at:
- /admin/settings: General, timetable, access, and integration settings
- /admin/data-management: Discovery, dry-run preview, and safe transactional clear of operational data
"""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.models.identity import User
from backend.schemas.settings import (
    DataClearExecuteRequest,
    DataClearExecuteResponse,
    DataClearPreviewRequest,
    DataClearPreviewResponse,
    DataManagementSummaryResponse,
    FullSettingsResponse,
    GeneralSettingsResponse,
    GeneralSettingsUpdate,
    SystemIntegrationStatus,
    TimetableSettingsResponse,
    TimetableSettingsUpdate,
)
from backend.services.settings_service import (
    execute_data_clear,
    get_data_management_summary,
    get_general_settings,
    get_system_integration_status,
    get_timetable_settings,
    get_user_access_summary,
    preview_data_clear,
    update_general_settings,
    update_timetable_settings,
)

router = APIRouter(prefix="/admin", tags=["Settings & Data Management"])


@router.get(
    "/settings",
    response_model=FullSettingsResponse,
    summary="Get complete administrative system settings overview",
)
def get_full_settings(
    response: Response,
    current_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> FullSettingsResponse:
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    general = get_general_settings(db)
    timetable = get_timetable_settings(db)
    access = get_user_access_summary(db)
    system = get_system_integration_status()
    return FullSettingsResponse(
        general=general,
        timetable=timetable,
        access=access,
        system=system,
    )


@router.patch(
    "/settings/general",
    response_model=GeneralSettingsResponse,
    summary="Update general institutional settings and notification preferences",
)
def patch_general_settings(
    payload: GeneralSettingsUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> GeneralSettingsResponse:
    return update_general_settings(db, payload, current_user)


@router.patch(
    "/settings/timetable",
    response_model=TimetableSettingsResponse,
    summary="Update timetable scheduling constraints and default preferences",
)
def patch_timetable_settings(
    payload: TimetableSettingsUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> TimetableSettingsResponse:
    return update_timetable_settings(db, payload, current_user)


@router.get(
    "/system/status",
    response_model=SystemIntegrationStatus,
    summary="Get live database, AI agent, and infrastructure health status",
)
def get_system_status(
    current_user: User = Depends(require_role("ADMIN")),
) -> SystemIntegrationStatus:
    return get_system_integration_status()


# ── Data Management & Safe Operational Reset ─────────────────────────────────

@router.get(
    "/data-management/summary",
    response_model=DataManagementSummaryResponse,
    summary="Get record counts and status for all generated operational data categories",
)
def get_data_summary(
    response: Response,
    current_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> DataManagementSummaryResponse:
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return get_data_management_summary(db)


@router.post(
    "/data-management/preview",
    response_model=DataClearPreviewResponse,
    summary="Generate a dry-run preview before clearing operational data",
)
def post_data_preview(
    payload: DataClearPreviewRequest,
    current_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> DataClearPreviewResponse:
    return preview_data_clear(db, payload.categories, payload.clear_all)


@router.post(
    "/data-management/clear",
    response_model=DataClearExecuteResponse,
    summary="Execute controlled transactional deletion of selected generated operational data",
)
def post_data_clear(
    payload: DataClearExecuteRequest,
    current_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> DataClearExecuteResponse:
    if not payload.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit confirmation (confirmation: true) is required to execute a data clear operation.",
        )
    if not payload.clear_all and not payload.categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one category or clear_all must be specified.",
        )

    return execute_data_clear(db, payload.categories, payload.clear_all, current_user)

