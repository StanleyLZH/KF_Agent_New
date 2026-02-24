"""流程编辑器辅助 API：文件上传、控件拾取、窗口截屏、服务器端目录浏览。"""
import asyncio
import logging
import string
import sys
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from kf_agent.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _platforms_dir() -> Path:
    return get_settings().platforms_dir


def _templates_dir() -> Path:
    return _platforms_dir() / "templates"


def _bin_dir() -> Path:
    """可执行文件上传目录（用于 launch 路径）。"""
    d = _platforms_dir() / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_browser_roots() -> list[dict[str, Any]]:
    """返回服务器端文件系统根目录列表（用于 launch 选择可执行文件）。"""
    if sys.platform == "win32":
        roots = [
            {"name": f"{d}:\\", "path": f"{d}:\\", "is_dir": True}
            for d in string.ascii_uppercase
            if Path(f"{d}:\\").exists()
        ]
    else:
        roots = [{"name": "/", "path": "/", "is_dir": True}]
    return roots


def _list_dir_entries(dir_path: Path) -> list[dict[str, Any]]:
    """列出目录下的条目（目录在前，可执行文件在后，其余文件最后）。"""
    exe_suffixes = (".exe", ".bat", ".cmd")
    dirs: list[dict[str, Any]] = []
    exe_files: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    try:
        for p in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            name = p.name
            abs_path = str(p.resolve())
            is_dir = p.is_dir()
            if is_dir:
                dirs.append({"name": name, "path": abs_path, "is_dir": True})
            else:
                entry = {"name": name, "path": abs_path, "is_dir": False}
                if name.lower().endswith(exe_suffixes):
                    exe_files.append(entry)
                else:
                    other.append(entry)
    except OSError as e:
        logger.warning("list_dir %s: %s", dir_path, e)
        raise HTTPException(status_code=400, detail=str(e))
    return dirs + exe_files + other


@router.get("/list-dir")
async def list_dir(path: str = Query("", description="目录绝对路径，空则返回根列表（如 C:\\\\、/）")):
    """列出远程服务器上某目录下的子目录与文件，用于 launch 步骤从服务器端选择可执行文件。"""
    if not path or not path.strip():
        return {"roots": _file_browser_roots()}
    p = Path(path.strip())
    if not p.is_absolute():
        return {"roots": _file_browser_roots()}
    if not p.exists():
        raise HTTPException(status_code=404, detail="path not found")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")
    return {"entries": _list_dir_entries(p), "current": str(p.resolve())}


@router.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):
    """上传可执行文件，保存到 platforms/bin/，返回服务器上的绝对路径（用于 launch 步骤）。保留接口以兼容旧版。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="no filename")
    dest = _bin_dir() / file.filename
    try:
        content = await file.read()
        dest.write_bytes(content)
        return {"path": str(dest.resolve())}
    except Exception as e:
        logger.exception("upload_file: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-template")
async def upload_template(file: UploadFile = File(...)):
    """上传图片模板，保存到 platforms/templates/，返回文件名（用于 click/input_text 图像定位）。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="no filename")
    _templates_dir().mkdir(parents=True, exist_ok=True)
    dest = _templates_dir() / file.filename
    try:
        content = await file.read()
        dest.write_bytes(content)
        return {"filename": file.filename}
    except Exception as e:
        logger.exception("upload_template: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _get_control_at_cursor() -> Optional[dict[str, Any]]:
    """Windows：获取当前鼠标位置的控件属性。非 Windows 返回 None。"""
    if sys.platform != "win32":
        return None
    try:
        import pyautogui
        x, y = pyautogui.position()
    except Exception as e:
        logger.warning("get cursor position: %s", e)
        return None
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        elem = desktop.from_point(x, y)
        if elem is None:
            return None
        window_title: Optional[str] = None
        window_class: Optional[str] = None
        control_id: Optional[int] = None
        automation_id: Optional[str] = None
        control_type: Optional[str] = None
        name: Optional[str] = None
        try:
            top = desktop.top_from_point(x, y)
            if top is not None:
                tw = top.wrapper_object()
                window_title = tw.window_text() or None
                window_class = tw.class_name() or None
        except Exception:
            pass
        try:
            w = elem.wrapper_object()
            name = w.window_text() or None
            if window_class is None:
                window_class = w.class_name() or None
        except Exception:
            pass
        try:
            ei = elem.element_info
            if hasattr(ei, "control_id"):
                control_id = getattr(ei, "control_id", None)
            if hasattr(ei, "automation_id"):
                automation_id = getattr(ei, "automation_id", None)
            elif hasattr(ei, "auto_id"):
                automation_id = getattr(ei, "auto_id", None)
            if hasattr(ei, "control_type"):
                ct = getattr(ei, "control_type", None)
                control_type = str(ct) if ct else None
            if name is None and hasattr(ei, "name"):
                name = getattr(ei, "name", None)
        except Exception:
            pass
        return {
            "window_title": window_title,
            "window_class": window_class,
            "control_id": control_id,
            "automation_id": automation_id,
            "control_type": control_type,
            "name": name,
        }
    except Exception as e:
        logger.warning("get_control_at_cursor: %s", e)
        return None


@router.get("/pick-control")
async def pick_control():
    """
    获取当前鼠标位置的控件属性（仅 Windows，需 pywinauto）。
    保留用于兼容；推荐使用 POST /pick-control/capture（红框 + Ctrl+点击 捕获）。
    """
    out = _get_control_at_cursor()
    if out is None:
        raise HTTPException(
            status_code=501,
            detail="pick-control is only supported on Windows with pywinauto, or no control at cursor",
        )
    return out


@router.post("/pick-control/capture")
async def pick_control_capture():
    """
    开始控件捕获会话（仅 Windows）：
    点击「开始捕获」后，桌面会显示鼠标所在控件的红框；按 Ctrl+Shift+C 可捕获该控件。
    建议先最小化编辑器窗口再操作。
    """
    if sys.platform != "win32":
        raise HTTPException(
            status_code=501,
            detail="pick-control/capture is only supported on Windows",
        )
    try:
        from kf_agent.api.win_control_picker import run_pick_control_session
    except ImportError as e:
        logger.warning("win_control_picker import: %s", e)
        raise HTTPException(
            status_code=501,
            detail="control picker requires pywinauto and pyautogui",
        ) from e
    loop = asyncio.get_event_loop()
    out = await loop.run_in_executor(None, lambda: run_pick_control_session(timeout=120.0))
    if out is None:
        return {"captured": False, "detail": "timeout_or_no_control"}
    return out


def _capture_foreground_window() -> Optional[Path]:
    """Windows：截取当前前台窗口，保存到 templates，返回文件路径。"""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        left, top = rect.left, rect.top
        right, bottom = rect.right, rect.bottom
        if right <= left or bottom <= top:
            return None
    except Exception as e:
        logger.warning("get window rect: %s", e)
        return None
    try:
        from PIL import ImageGrab
        bbox = (left, top, right, bottom)
        img = ImageGrab.grab(bbox=bbox)
        _templates_dir().mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = _templates_dir() / f"capture_{ts}.png"
        img.save(str(path))
        return path
    except Exception as e:
        logger.warning("capture window: %s", e)
        return None


@router.get("/templates/{filename:path}")
async def get_template_image(filename: str):
    """获取模板图片（用于预览）。"""
    base = _templates_dir().resolve()
    path = (base / filename).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise HTTPException(status_code=404, detail="template not found")
    return FileResponse(path)


@router.post("/capture-window")
async def capture_window():
    """
    截取当前前台窗口，保存到 platforms/templates/，返回文件名（仅 Windows）。
    使用方式：先切换到客服软件目标窗口，再点击编辑器中的「从当前窗口截取」。
    """
    path = _capture_foreground_window()
    if path is None:
        raise HTTPException(
            status_code=501,
            detail="capture-window is only supported on Windows with PIL",
        )
    return {"filename": path.name}


@router.post("/capture-region")
async def capture_region():
    """
    区域截图（仅 Windows）：点击「从当前窗口截取」后本窗口会最小化，
    请先切换到目标窗口，再按 Ctrl+Shift+R 开始框选；出现遮罩后按住 Ctrl 拖动框选区域，松开即保存。
    按 Esc 取消。返回保存的文件名。
    """
    if sys.platform != "win32":
        raise HTTPException(
            status_code=501,
            detail="capture-region is only supported on Windows",
        )
    try:
        from kf_agent.api.win_region_capture import run_capture_region_session
    except ImportError as e:
        logger.warning("win_region_capture import: %s", e)
        raise HTTPException(
            status_code=501,
            detail="region capture requires Windows",
        ) from e
    templates_dir = _templates_dir()
    loop = asyncio.get_event_loop()
    path = await loop.run_in_executor(
        None,
        lambda: run_capture_region_session(templates_dir, timeout=120.0),
    )
    if path is None:
        raise HTTPException(
            status_code=408,
            detail="region capture timeout or cancelled (switch to target window then press Ctrl+Shift+R, then Ctrl+drag to select; Esc to cancel)",
        )
    return {"filename": path.name}
