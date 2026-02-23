"""配置 CRUD 接口：获取/更新某平台的流程与元素配置。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Optional

from kf_agent.core.models import PlatformConfig
from kf_agent.storage import platform_config as storage

router = APIRouter()


class PlatformConfigUpdate(BaseModel):
    open: list[dict[str, Any]] = Field(default_factory=list, description="打开流程步骤列表")
    close: list[dict[str, Any]] = Field(default_factory=list, description="关闭流程步骤列表")
    display_name: Optional[str] = None


@router.get("/platforms/{platform_id}")
async def get_platform_config(platform_id: str):
    config = storage.load_platform_config(platform_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"platform not found: {platform_id}")
    return config.model_dump()


@router.put("/platforms/{platform_id}")
async def update_platform_config(platform_id: str, body: PlatformConfigUpdate):
    config = PlatformConfig(
        platform=platform_id,
        open=body.open,
        close=body.close,
        display_name=body.display_name,
    )
    ok = storage.save_platform_config(config)
    if not ok:
        raise HTTPException(status_code=500, detail="save failed")
    return {"platform": platform_id, "updated": True}


@router.delete("/platforms/{platform_id}")
async def delete_platform_config(platform_id: str):
    ok = storage.delete_platform_config(platform_id)
    if not ok:
        raise HTTPException(status_code=500, detail="delete failed")
    return {"platform": platform_id, "deleted": True}
