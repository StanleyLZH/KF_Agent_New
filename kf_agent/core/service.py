"""业务服务层：打开/关闭流程编排，调用引擎与存储。"""
import logging
from pathlib import Path
from typing import Optional

from kf_agent.config import get_settings
from kf_agent.core.engine import run_steps, EngineError
from kf_agent.core.models import PlatformConfig
from kf_agent.drivers import get_default_driver
from kf_agent.storage.platform_config import load_platform_config, list_platform_ids

logger = logging.getLogger(__name__)


def _templates_base() -> Path:
    settings = get_settings()
    return settings.platforms_dir / settings.templates_dir_name


def open_platform(platform_id: str) -> dict:
    """
    执行该平台的 open 流程。返回 {"success": bool, "message": str}。
    """
    config = load_platform_config(platform_id)
    if not config:
        return {"success": False, "message": f"platform config not found: {platform_id}"}
    steps = config.get_open_steps()
    if not steps:
        return {"success": False, "message": "open flow is empty"}
    try:
        driver = get_default_driver()
        run_steps(steps, driver, templates_base=_templates_base())
        return {"success": True, "message": "ok"}
    except EngineError as e:
        logger.exception("open_platform engine error: %s", e)
        return {"success": False, "message": str(e)}
    except Exception as e:
        logger.exception("open_platform error: %s", e)
        return {"success": False, "message": str(e)}


def close_platform(platform_id: str) -> dict:
    """执行该平台的 close 流程。"""
    config = load_platform_config(platform_id)
    if not config:
        return {"success": False, "message": f"platform config not found: {platform_id}"}
    steps = config.get_close_steps()
    if not steps:
        return {"success": False, "message": "close flow is empty"}
    try:
        driver = get_default_driver()
        run_steps(steps, driver, templates_base=_templates_base())
        return {"success": True, "message": "ok"}
    except EngineError as e:
        logger.exception("close_platform engine error: %s", e)
        return {"success": False, "message": str(e)}
    except Exception as e:
        logger.exception("close_platform error: %s", e)
        return {"success": False, "message": str(e)}


def get_platform_status(platform_id: str) -> dict:
    """
    返回该平台状态。当前简化：仅表示配置是否存在；后续可加进程/窗口检测。
    """
    config = load_platform_config(platform_id)
    if not config:
        return {"configured": False, "running": False, "online": False}
    return {
        "configured": True,
        "running": False,  # TODO: 根据进程或窗口检测
        "online": False,   # TODO: 根据界面状态检测
    }


def get_platforms_list() -> list[dict]:
    """返回已配置平台列表，每项含 platform_id、display_name。"""
    ids = list_platform_ids()
    result = []
    for pid in ids:
        config = load_platform_config(pid)
        result.append({
            "platform": pid,
            "display_name": config.display_name if config else pid,
        })
    return result
