"""图像模板匹配 + 点击（OpenCV + PyAutoGUI）。"""
import logging
from pathlib import Path
from typing import Optional, Tuple

from kf_agent.drivers.base import UIDriver

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    import pyautogui
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False
    cv2 = None
    np = None
    pyautogui = None


def _locate_image_opencv(image_path: str, threshold: float = 0.8) -> Optional[Tuple[int, int]]:
    """使用 OpenCV 模板匹配，返回匹配区域中心 (x, y)，未找到返回 None。"""
    if not _CV2_AVAILABLE or cv2 is None or np is None:
        return None
    path = Path(image_path)
    if not path.exists():
        logger.warning("template image not found: %s", image_path)
        return None
    try:
        template = cv2.imread(str(path))
        if template is None:
            return None
        screen = pyautogui.screenshot()
        screen_cv = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
        result = cv2.matchTemplate(screen_cv, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val < threshold:
            return None
        h, w = template.shape[:2]
        cx = max_loc[0] + w // 2
        cy = max_loc[1] + h // 2
        return (cx, cy)
    except Exception as e:
        logger.warning("opencv locate failed: %s", e)
        return None


def _locate_image_pyautogui(image_path: str) -> Optional[Tuple[int, int]]:
    """使用 PyAutoGUI 的 locateOnScreen（PIL 匹配），返回中心。"""
    if not _CV2_AVAILABLE or pyautogui is None:
        return None
    path = Path(image_path)
    if not path.exists():
        return None
    try:
        try:
            loc = pyautogui.locateOnScreen(str(path), confidence=0.8)
        except TypeError:
            loc = pyautogui.locateOnScreen(str(path))
        if loc is None:
            return None
        return (loc.left + loc.width // 2, loc.top + loc.height // 2)
    except Exception as e:
        logger.debug("pyautogui locate failed: %s", e)
        return None


class ImageClickDriver(UIDriver):
    """仅实现图像定位 + 点击与键盘；启动/窗口等待/关窗由调用方或组合驱动实现。"""

    def __init__(self):
        if not _CV2_AVAILABLE or pyautogui is None:
            raise RuntimeError("image_click driver requires opencv-python and pyautogui")

    def launch(self, path: str, args: Optional[list[str]] = None, cwd: Optional[str] = None) -> None:
        import subprocess
        cmd = [path]
        if args:
            cmd.extend(args)
        subprocess.Popen(cmd, cwd=cwd, shell=False)

    def wait_window(
        self,
        title: Optional[str] = None,
        class_name: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ) -> bool:
        import time
        time.sleep(min(3.0, timeout_seconds))
        return True

    def click(self, x: int, y: int) -> None:
        pyautogui.click(x, y)

    def find_and_click_image(self, image_path: str, threshold: float = 0.8) -> bool:
        center = _locate_image_opencv(image_path, threshold)
        if center is None:
            center = _locate_image_pyautogui(image_path)
        if center is None:
            return False
        pyautogui.click(center[0], center[1])
        return True

    def type_text(self, text: str) -> None:
        pyautogui.write(text, interval=0.05)

    def hotkey(self, *keys: str) -> None:
        pyautogui.hotkey(*keys)

    def close_window(
        self,
        title: Optional[str] = None,
        class_name: Optional[str] = None,
        kill_process: bool = False,
    ) -> bool:
        if kill_process and title:
            try:
                import psutil
                for p in psutil.process_iter(["name", "pid"]):
                    if title.lower() in (p.info.get("name") or "").lower():
                        p.terminate()
                        return True
            except Exception as e:
                logger.warning("close_window kill_process: %s", e)
        return False
