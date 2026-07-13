from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth.dependencies import set_dashboard_error_format, validate_dashboard_session
from app.modules.system_status.schemas import SystemStatusResponse
from app.modules.system_status.service import get_system_status

router = APIRouter(
    prefix="/api",
    tags=["system-status"],
    dependencies=[Depends(validate_dashboard_session), Depends(set_dashboard_error_format)],
)


@router.get("/system-status", response_model=SystemStatusResponse)
async def read_system_status() -> SystemStatusResponse:
    return get_system_status()
