"""Windows UI 自动化（pywinauto）：窗口等待、关窗、可选控件点击。"""
import logging
import re
import subprocess
import sys
import time
from typing import Optional

from kf_agent.core.models import ElementControl
from kf_agent.drivers.base import UIDriver

logger = logging.getLogger(__name__)

_PYWINAUTO_AVAILABLE = False
try:
    from pywinauto import Application
    from pywinauto.findwindows import ElementNotFoundError
    _PYWINAUTO_AVAILABLE = True
except ImportError:
    Application = None
    ElementNotFoundError = Exception


def _get_fallback_driver() -> UIDriver:
    """无 pywinauto 时回退到图像+坐标驱动。"""
    from kf_agent.drivers.image_click import ImageClickDriver
    return ImageClickDriver()


class WinAutomationDriver(UIDriver):
    """Windows 下使用 pywinauto 等待/关窗，点击与键盘可委托给 ImageClickDriver。"""

    def __init__(self, use_image_for_click: bool = True):
        self._fallback: Optional[UIDriver] = None
        if use_image_for_click or not _PYWINAUTO_AVAILABLE:
            try:
                self._fallback = _get_fallback_driver()
            except Exception as e:
                logger.warning("fallback ImageClickDriver not available: %s", e)
        self._app: Optional[Application] = None

    def _click_driver(self) -> UIDriver:
        if self._fallback is not None:
            return self._fallback
        raise RuntimeError("no click driver available")

    def launch(self, path: str, args: Optional[list[str]] = None, cwd: Optional[str] = None) -> None:
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
        if not _PYWINAUTO_AVAILABLE or Application is None:
            return self._click_driver().wait_window(title, class_name, timeout_seconds)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                if title:
                    self._app = Application(backend="uia").connect(title_re=f".*{re.escape(title)}.*", timeout=1)
                elif class_name:
                    self._app = Application(backend="uia").connect(class_name_re=f".*{re.escape(class_name)}.*", timeout=1)
                else:
                    return False
                if self._app and self._app.windows():
                    return True
            except ElementNotFoundError:
                time.sleep(0.5)
                continue
            except Exception as e:
                logger.debug("wait_window: %s", e)
                time.sleep(0.5)
        return False

    def click(self, x: int, y: int) -> None:
        self._click_driver().click(x, y)

    def find_and_click_image(self, image_path: str, threshold: float = 0.8) -> bool:
        return self._click_driver().find_and_click_image(image_path, threshold)

    def find_and_click_control(self, control: ElementControl) -> bool:
        """使用 pywinauto 查找控件并点击。需 Windows + pywinauto。"""
        if sys.platform != "win32" or not _PYWINAUTO_AVAILABLE or Application is None:
            return super().find_and_click_control(control)

        if not control.window_title and not control.window_class:
            logger.warning("find_and_click_control: need window_title or window_class")
            return False

        has_control_id = control.control_id is not None
        has_auto_id = bool(control.automation_id)
        has_control_type = bool(control.control_type)
        has_name = bool(control.name)
        if not (has_control_id or has_auto_id or has_control_type or has_name):
            logger.warning("find_and_click_control: need at least one of control_id, automation_id, control_type, name")
            return False

        try:
            app = Application(backend="uia")
            if control.window_title:
                app = app.connect(title_re=f".*{re.escape(control.window_title)}.*", timeout=5)
            else:
                app = app.connect(class_name_re=f".*{re.escape(control.window_class or '')}.*", timeout=5)

            win = app.windows()[0]
            candidates: list[dict] = []
            if has_auto_id and has_control_id:
                candidates.append({"auto_id": control.automation_id, "control_id": control.control_id})
            if has_auto_id and has_name:
                candidates.append({"auto_id": control.automation_id, "title_re": f".*{re.escape(control.name or '')}.*"})
            if has_control_id and has_name:
                candidates.append({"control_id": control.control_id, "title_re": f".*{re.escape(control.name or '')}.*"})
            if has_auto_id:
                candidates.append({"auto_id": control.automation_id})
            if has_control_id:
                candidates.append({"control_id": control.control_id})
            if has_name and has_control_type:
                candidates.append({"title_re": f".*{re.escape(control.name or '')}.*", "control_type": control.control_type})
            if has_name:
                candidates.append({"title_re": f".*{re.escape(control.name or '')}.*"})
            if has_control_type:
                candidates.append({"control_type": control.control_type})

            tried = set()
            for kwargs in candidates:
                key = tuple(sorted(kwargs.items()))
                if key in tried:
                    continue
                tried.add(key)
                try:
                    ctrl = win.child_window(**kwargs)
                    ctrl.click_input()
                    return True
                except Exception:
                    continue
            return False
        except ElementNotFoundError as e:
            logger.warning("find_and_click_control: element not found: %s", e)
            return False
        except Exception as e:
            logger.warning("find_and_click_control: %s", e)
            return False

    def type_text(self, text: str) -> None:
        self._click_driver().type_text(text)

    def hotkey(self, *keys: str) -> None:
        self._click_driver().hotkey(*keys)

    def close_window(
        self,
        title: Optional[str] = None,
        class_name: Optional[str] = None,
        kill_process: bool = False,
    ) -> bool:
        if kill_process:
            if self._fallback:
                return self._fallback.close_window(title, class_name, kill_process=True)
            return False
        if not _PYWINAUTO_AVAILABLE or Application is None or not title:
            return False
        try:
            app = Application(backend="uia").connect(title_re=f".*{re.escape(title)}.*", timeout=3)
            for w in app.windows():
                w.close()
                return True
        except Exception as e:
            logger.warning("close_window: %s", e)
        return False
