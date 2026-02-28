"""流程执行引擎：解析步骤类型并调用 UI 驱动执行。"""
import logging
import time
from pathlib import Path
from typing import Optional

from kf_agent.core.models import (
    StepLaunch,
    StepWaitWindow,
    StepClick,
    StepInputText,
    StepWait,
    StepHotkey,
    StepCloseWindow,
    step_from_dict,
)
from kf_agent.drivers.base import UIDriver

logger = logging.getLogger(__name__)


class EngineError(Exception):
    """步骤执行失败（如超时、找不到元素）。"""
    pass


def _resolve_image_path(relative_path: str, templates_base: Optional[Path]) -> str:
    """将相对路径解析为绝对路径。templates_base 为 platforms 目录或 platforms/templates。"""
    if not relative_path:
        return relative_path
    p = Path(relative_path)
    if p.is_absolute() and p.exists():
        return str(p)
    if templates_base is not None:
        full = templates_base / relative_path
        if full.exists():
            return str(full.resolve())
        # 尝试 platforms_dir 根下
        full = templates_base.parent / relative_path
        if full.exists():
            return str(full.resolve())
    return str(Path(relative_path).resolve() if p.is_absolute() else relative_path)


def run_steps(
    steps: list,
    driver: UIDriver,
    templates_base: Optional[Path] = None,
) -> None:
    """
    按顺序执行步骤列表。steps 为已解析的 Step* 模型列表。
    templates_base 用于解析 image 相对路径，通常为 platforms_dir 或 platforms_dir/templates。
    """
    for i, step in enumerate(steps):
        kind = getattr(step, "type", None)
        logger.info("engine step %s: type=%s", i + 1, kind)
        if kind == "launch":
            s = step  # type: StepLaunch
            driver.launch(s.path, args=s.args, cwd=s.cwd)
        elif kind == "wait_window":
            s = step  # type: StepWaitWindow
            ok = driver.wait_window(
                title=s.title,
                class_name=s.class_name,
                timeout_seconds=s.timeout_seconds,
            )
            if not ok:
                raise EngineError(f"wait_window timeout: title={s.title}")
        elif kind == "click":
            s = step  # type: StepClick
            if s.x is not None and s.y is not None:
                driver.click(s.x, s.y)
            elif s.element and s.element.has_any():
                el = s.element
                if el.coord is not None:
                    driver.click(el.coord.x, el.coord.y)
                elif el.image is not None:
                    path = _resolve_image_path(el.image.image, templates_base)
                    th = getattr(el.image, "threshold", 0.8) or 0.8
                    if not driver.find_and_click_image(path, threshold=th):
                        raise EngineError(f"image not found: {path}")
                elif el.control is not None:
                    try:
                        if not driver.find_and_click_control(el.control):
                            raise EngineError("control not found or click failed")
                    except NotImplementedError:
                        raise EngineError("control click not implemented in engine")
                else:
                    raise EngineError("click step has no coord, image, or control")
            else:
                raise EngineError("click step has no element or (x,y)")
        elif kind == "input_text":
            s = step  # type: StepInputText
            if s.element and s.element.has_any():
                # 先点击再输入（简化）
                el = s.element
                if el.coord is not None:
                    driver.click(el.coord.x, el.coord.y)
                    time.sleep(0.2)
                elif el.image is not None:
                    path = _resolve_image_path(el.image.image, templates_base)
                    th = getattr(el.image, "threshold", 0.8) or 0.8
                    if not driver.find_and_click_image(path, threshold=th):
                        raise EngineError(f"input_text image not found: {path}")
                    time.sleep(0.2)
                elif el.control is not None:
                    try:
                        if not driver.find_and_click_control(el.control):
                            raise EngineError("input_text control not found or click failed")
                    except NotImplementedError:
                        raise EngineError("control click not implemented in engine")
                    time.sleep(0.2)
            driver.type_text(s.text)
        elif kind == "wait":
            s = step  # type: StepWait
            time.sleep(s.seconds)
        elif kind == "hotkey":
            s = step  # type: StepHotkey
            driver.hotkey(*s.keys)
        elif kind == "close_window":
            s = step  # type: StepCloseWindow
            ok = driver.close_window(
                title=s.title,
                class_name=s.class_name,
                kill_process=s.kill_process,
            )
            if not ok and s.title:
                logger.warning("close_window may have failed: title=%s", s.title)
        else:
            raise EngineError(f"unknown step type: {kind}")
