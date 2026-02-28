"""按平台读写资源库 JSON。"""
import json
import logging
from pathlib import Path
from typing import Optional

from kf_agent.config import get_settings
from kf_agent.core.models import ResourceLibrary

logger = logging.getLogger(__name__)


def get_platforms_dir(platforms_dir: Optional[Path] = None) -> Path:
    if platforms_dir is not None:
        return Path(platforms_dir)
    return get_settings().platforms_dir


def path_for_platform_resources(platform_id: str, platforms_dir: Optional[Path] = None) -> Path:
    root = get_platforms_dir(platforms_dir)
    return root / f"{platform_id}.resources.json"


def load_resource_library(platform_id: str, platforms_dir: Optional[Path] = None) -> ResourceLibrary:
    """读取平台资源库，不存在时返回空资源库。"""
    path = path_for_platform_resources(platform_id, platforms_dir)
    if not path.exists():
        return ResourceLibrary(platform=platform_id)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        data.setdefault("platform", platform_id)
        return ResourceLibrary.model_validate(data)
    except Exception as e:
        logger.warning("load_resource_library failed: %s path=%s", e, path)
        return ResourceLibrary(platform=platform_id)


def save_resource_library(library: ResourceLibrary, platforms_dir: Optional[Path] = None) -> bool:
    """保存平台资源库（原子替换）。"""
    path = path_for_platform_resources(library.platform, platforms_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = library.model_dump_json(indent=2, ensure_ascii=False)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception as e:
        logger.warning("save_resource_library failed: %s path=%s", e, path)
        return False

