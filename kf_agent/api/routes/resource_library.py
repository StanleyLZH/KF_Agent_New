"""平台资源库 API：控件/图片资源的 CRUD 与定位。"""
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kf_agent.config import get_settings
from kf_agent.core.models import ElementControl, ElementImage, ResourceControlItem, ResourceImageItem
from kf_agent.storage import resource_library as storage

logger = logging.getLogger(__name__)
router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid4().hex[:12]


def _resolve_image_path(image_path: str) -> Path:
    p = Path(image_path)
    if p.is_absolute() and p.exists():
        return p
    settings = get_settings()
    templates_dir = settings.platforms_dir / settings.templates_dir_name
    candidate = templates_dir / image_path
    if candidate.exists():
        return candidate
    candidate = settings.platforms_dir / image_path
    if candidate.exists():
        return candidate
    return p


def _locate_control_rect(control: ElementControl) -> Optional[tuple[int, int, int, int]]:
    try:
        from pywinauto import Application
        from pywinauto.findwindows import ElementNotFoundError
    except ImportError:
        return None

    if not control.window_title and not control.window_class:
        return None

    try:
        app = Application(backend="uia")
        if control.window_title:
            app = app.connect(title_re=f".*{re.escape(control.window_title)}.*", timeout=5)
        else:
            app = app.connect(class_name_re=f".*{re.escape(control.window_class or '')}.*", timeout=5)

        win = app.windows()[0]
        if (
            control.control_id is None
            and not control.automation_id
            and not control.control_type
            and not control.name
        ):
            return None

        # 先严格后宽松，避免捕获信息轻微变化导致定位失败
        candidates: list[dict] = []
        if control.automation_id and control.control_id is not None:
            candidates.append({"auto_id": control.automation_id, "control_id": control.control_id})
        if control.automation_id and control.name:
            candidates.append({"auto_id": control.automation_id, "title_re": f".*{re.escape(control.name)}.*"})
        if control.control_id is not None and control.name:
            candidates.append({"control_id": control.control_id, "title_re": f".*{re.escape(control.name)}.*"})
        if control.automation_id:
            candidates.append({"auto_id": control.automation_id})
        if control.control_id is not None:
            candidates.append({"control_id": control.control_id})
        if control.name and control.control_type:
            candidates.append({"title_re": f".*{re.escape(control.name)}.*", "control_type": control.control_type})
        if control.name:
            candidates.append({"title_re": f".*{re.escape(control.name)}.*"})
        if control.control_type:
            candidates.append({"control_type": control.control_type})

        tried = set()
        for kwargs in candidates:
            key = tuple(sorted(kwargs.items()))
            if key in tried:
                continue
            tried.add(key)
            try:
                ctrl = win.child_window(**kwargs).wrapper_object()
                rect = ctrl.rectangle()
                return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            except Exception:
                continue
        return None
    except ElementNotFoundError:
        return None
    except Exception as e:
        logger.warning("locate control failed: %s", e)
        return None


def _locate_image_rect(image: ElementImage) -> tuple[Optional[tuple[int, int, int, int]], Optional[float]]:
    try:
        import cv2
        import numpy as np
        import pyautogui
    except ImportError:
        return None, None

    path = _resolve_image_path(image.image)
    if not path.exists():
        return None, None

    try:
        template = cv2.imread(str(path))
        if template is None:
            return None, None
        screen = pyautogui.screenshot()
        screen_cv = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
        result = cv2.matchTemplate(screen_cv, template, cv2.TM_CCOEFF_NORMED)
        _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val < (image.threshold or 0.8):
            return None, float(max_val)
        h, w = template.shape[:2]
        rect = (int(max_loc[0]), int(max_loc[1]), int(max_loc[0] + w), int(max_loc[1] + h))
        return rect, float(max_val)
    except Exception as e:
        logger.warning("locate image failed: %s", e)
        return None, None


def _blink_rect(rect: tuple[int, int, int, int]) -> bool:
    try:
        from kf_agent.api.win_overlay_highlight import blink_rect

        return blink_rect(rect, duration_seconds=2.4, interval_seconds=0.24, border_px=3)
    except Exception as e:
        logger.warning("blink rect failed: %s", e)
        return False


class CreateControlResourceBody(BaseModel):
    name: str = Field(..., min_length=1, description="资源名称")
    payload: ElementControl


class CreateImageResourceBody(BaseModel):
    name: str = Field(..., min_length=1, description="资源名称")
    payload: ElementImage


class RenameResourceBody(BaseModel):
    name: str = Field(..., min_length=1, description="新名称")


class LocateResourceBody(BaseModel):
    type: Literal["control", "image"]
    resource_id: str


@router.get("/platforms/{platform_id}/resources")
async def get_resources(platform_id: str):
    library = storage.load_resource_library(platform_id)
    return library.model_dump()


@router.post("/platforms/{platform_id}/resources/controls")
async def create_control_resource(platform_id: str, body: CreateControlResourceBody):
    library = storage.load_resource_library(platform_id)
    now = _now_iso()
    item = ResourceControlItem(
        id=_new_id(),
        name=body.name.strip(),
        payload=body.payload,
        created_at=now,
        updated_at=now,
    )
    library.controls.append(item)
    if not storage.save_resource_library(library):
        raise HTTPException(status_code=500, detail="save resource failed")
    return item.model_dump()


@router.post("/platforms/{platform_id}/resources/images")
async def create_image_resource(platform_id: str, body: CreateImageResourceBody):
    library = storage.load_resource_library(platform_id)
    now = _now_iso()
    item = ResourceImageItem(
        id=_new_id(),
        name=body.name.strip(),
        payload=body.payload,
        created_at=now,
        updated_at=now,
    )
    library.images.append(item)
    if not storage.save_resource_library(library):
        raise HTTPException(status_code=500, detail="save resource failed")
    return item.model_dump()


@router.patch("/platforms/{platform_id}/resources/{resource_type}/{resource_id}/name")
async def rename_resource(
    platform_id: str,
    resource_type: Literal["controls", "images"],
    resource_id: str,
    body: RenameResourceBody,
):
    library = storage.load_resource_library(platform_id)
    now = _now_iso()
    if resource_type == "controls":
        items = library.controls
    else:
        items = library.images

    for item in items:
        if item.id == resource_id:
            item.name = body.name.strip()
            item.updated_at = now
            if not storage.save_resource_library(library):
                raise HTTPException(status_code=500, detail="save resource failed")
            return item.model_dump()
    raise HTTPException(status_code=404, detail="resource not found")


@router.delete("/platforms/{platform_id}/resources/{resource_type}/{resource_id}")
async def delete_resource(platform_id: str, resource_type: Literal["controls", "images"], resource_id: str):
    library = storage.load_resource_library(platform_id)
    if resource_type == "controls":
        before = len(library.controls)
        library.controls = [x for x in library.controls if x.id != resource_id]
        changed = len(library.controls) != before
    else:
        before = len(library.images)
        library.images = [x for x in library.images if x.id != resource_id]
        changed = len(library.images) != before

    if not changed:
        raise HTTPException(status_code=404, detail="resource not found")
    if not storage.save_resource_library(library):
        raise HTTPException(status_code=500, detail="save resource failed")
    return {"deleted": True, "resource_id": resource_id}


@router.post("/platforms/{platform_id}/resources/locate")
async def locate_resource(platform_id: str, body: LocateResourceBody):
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="locate is only supported on Windows")

    library = storage.load_resource_library(platform_id)
    if body.type == "control":
        item = next((x for x in library.controls if x.id == body.resource_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="control resource not found")
        rect = _locate_control_rect(item.payload)
        if rect is None:
            raise HTTPException(status_code=404, detail="control not found on current desktop")
        _blink_rect(rect)
        return {
            "matched": True,
            "type": "control",
            "resource_id": item.id,
            "name": item.name,
            "rect": {"left": rect[0], "top": rect[1], "right": rect[2], "bottom": rect[3]},
        }

    item = next((x for x in library.images if x.id == body.resource_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="image resource not found")
    rect, score = _locate_image_rect(item.payload)
    if rect is None:
        raise HTTPException(status_code=404, detail="image not found on screen")
    _blink_rect(rect)
    return {
        "matched": True,
        "type": "image",
        "resource_id": item.id,
        "name": item.name,
        "score": score,
        "rect": {"left": rect[0], "top": rect[1], "right": rect[2], "bottom": rect[3]},
    }

