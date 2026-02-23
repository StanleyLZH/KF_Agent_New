"""流程、步骤、元素等 Pydantic 模型（可视化定制的数据基础）。"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------- 元素描述（与可视化定制对应） ----------


class ElementCoord(BaseModel):
    """屏幕或窗口相对坐标。"""
    x: int
    y: int
    relative_to: Literal["screen", "window"] = "screen"
    window_title: Optional[str] = None  # relative_to=window 时可选


class ElementImage(BaseModel):
    """图像模板定位：小图路径 + 匹配阈值。"""
    image: str  # 相对 platforms/templates 或绝对路径
    threshold: float = 0.8


class ElementControl(BaseModel):
    """控件定位（如 pywinauto）：窗口标题/类名 + 控件标识。"""
    window_title: Optional[str] = None
    window_class: Optional[str] = None
    control_id: Optional[int] = None
    automation_id: Optional[str] = None
    control_type: Optional[str] = None
    name: Optional[str] = None


class ElementDesc(BaseModel):
    """元素描述：坐标 / 图像 / 控件，至少一种。支持 image 简写为字符串路径。"""
    coord: Optional[ElementCoord] = None
    image: Optional[ElementImage] = None
    control: Optional[ElementControl] = None

    @field_validator("image", mode="before")
    @classmethod
    def normalize_image(cls, v: Any) -> Optional[ElementImage]:
        if v is None:
            return None
        if isinstance(v, str):
            return ElementImage(image=v)
        return v

    def has_any(self) -> bool:
        return self.coord is not None or self.image is not None or self.control is not None


# ---------- 步骤类型 ----------


StepType = Literal[
    "launch",
    "wait_window",
    "click",
    "input_text",
    "wait",
    "hotkey",
    "close_window",
]


class StepLaunch(BaseModel):
    type: Literal["launch"] = "launch"
    path: str
    args: Optional[list[str]] = None
    cwd: Optional[str] = None


class StepWaitWindow(BaseModel):
    type: Literal["wait_window"] = "wait_window"
    title: Optional[str] = None
    class_name: Optional[str] = None
    timeout_seconds: float = 30.0


class StepClick(BaseModel):
    type: Literal["click"] = "click"
    element: Optional[ElementDesc] = None
    # 无 element 时可用简单坐标（兼容旧配置）
    x: Optional[int] = None
    y: Optional[int] = None


class StepInputText(BaseModel):
    type: Literal["input_text"] = "input_text"
    element: Optional[ElementDesc] = None
    text: str = ""
    clear_first: bool = True


class StepWait(BaseModel):
    type: Literal["wait"] = "wait"
    seconds: float = 1.0


class StepHotkey(BaseModel):
    type: Literal["hotkey"] = "hotkey"
    keys: list[str]  # e.g. ["ctrl", "c"]


class StepCloseWindow(BaseModel):
    type: Literal["close_window"] = "close_window"
    title: Optional[str] = None
    class_name: Optional[str] = None
    kill_process: bool = False  # True 时直接结束进程


# 步骤联合类型（JSON 解析时用 dict + type 分发）
StepPayload = (
    StepLaunch
    | StepWaitWindow
    | StepClick
    | StepInputText
    | StepWait
    | StepHotkey
    | StepCloseWindow
)


def step_from_dict(data: dict[str, Any]) -> BaseModel:
    """从 JSON 字典解析为对应步骤模型。"""
    t = data.get("type")
    if t == "launch":
        return StepLaunch.model_validate(data)
    if t == "wait_window":
        return StepWaitWindow.model_validate(data)
    if t == "click":
        return StepClick.model_validate(data)
    if t == "input_text":
        return StepInputText.model_validate(data)
    if t == "wait":
        return StepWait.model_validate(data)
    if t == "hotkey":
        return StepHotkey.model_validate(data)
    if t == "close_window":
        return StepCloseWindow.model_validate(data)
    raise ValueError(f"unknown step type: {t}")


# ---------- 平台流程配置 ----------


class PlatformConfig(BaseModel):
    """单平台配置：open / close 流程。"""
    platform: str
    open: list[dict[str, Any]] = Field(default_factory=list)  # 步骤 JSON 列表
    close: list[dict[str, Any]] = Field(default_factory=list)
    display_name: Optional[str] = None  # 展示用名称，如「千牛」

    def get_open_steps(self) -> list[BaseModel]:
        return [step_from_dict(s) for s in self.open]

    def get_close_steps(self) -> list[BaseModel]:
        return [step_from_dict(s) for s in self.close]
