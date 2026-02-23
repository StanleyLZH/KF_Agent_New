"""UI 驱动抽象接口：定位、点击、输入、快捷键、窗口启停。"""
from abc import ABC, abstractmethod
from typing import Optional


class UIDriver(ABC):
    """统一 UI 驱动接口，供流程引擎调用。"""

    @abstractmethod
    def launch(self, path: str, args: Optional[list[str]] = None, cwd: Optional[str] = None) -> None:
        """启动进程。"""
        ...

    @abstractmethod
    def wait_window(
        self,
        title: Optional[str] = None,
        class_name: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ) -> bool:
        """等待窗口出现，超时返回 False。"""
        ...

    @abstractmethod
    def click(self, x: int, y: int) -> None:
        """屏幕坐标点击。"""
        ...

    @abstractmethod
    def find_and_click_image(self, image_path: str, threshold: float = 0.8) -> bool:
        """图像模板匹配并点击中心，未找到返回 False。"""
        ...

    @abstractmethod
    def type_text(self, text: str) -> None:
        """在当前焦点输入文本。"""
        ...

    @abstractmethod
    def hotkey(self, *keys: str) -> None:
        """按下快捷键。"""
        ...

    @abstractmethod
    def close_window(
        self,
        title: Optional[str] = None,
        class_name: Optional[str] = None,
        kill_process: bool = False,
    ) -> bool:
        """关闭窗口或结束进程，成功返回 True。"""
        ...
