# Drivers package
import sys

from kf_agent.drivers.base import UIDriver


def get_default_driver() -> UIDriver:
    """Windows 优先使用 WinAutomationDriver，否则使用 ImageClickDriver。"""
    if sys.platform == "win32":
        try:
            from kf_agent.drivers.win_automation import WinAutomationDriver
            return WinAutomationDriver(use_image_for_click=True)
        except Exception:
            pass
    from kf_agent.drivers.image_click import ImageClickDriver
    return ImageClickDriver()
