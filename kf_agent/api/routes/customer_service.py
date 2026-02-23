"""打开/关闭/状态/平台列表接口。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kf_agent.core import service

router = APIRouter()


class OpenRequest(BaseModel):
    platform: str = Field(..., description="平台 ID，如 qianniu、xiaohongshu、douyin")


class CloseRequest(BaseModel):
    platform: str = Field(..., description="平台 ID")


@router.post("/open")
async def open_customer_service(body: OpenRequest):
    result = service.open_platform(body.platform)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/close")
async def close_customer_service(body: CloseRequest):
    result = service.close_platform(body.platform)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/status")
async def get_status(platform: str):
    return service.get_platform_status(platform)


@router.get("/platforms")
async def list_platforms():
    return {"platforms": [p["platform"] for p in service.get_platforms_list()]}
