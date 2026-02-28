"""按平台读写 JSON 配置。"""
import json
import logging
from pathlib import Path
from typing import Optional

from kf_agent.core.models import PlatformConfig
from kf_agent.config import get_settings

logger = logging.getLogger(__name__)


def get_platforms_dir(platforms_dir: Optional[Path] = None) -> Path:
    if platforms_dir is not None:
        return Path(platforms_dir)
    return get_settings().platforms_dir


def path_for_platform(platform_id: str, platforms_dir: Optional[Path] = None) -> Path:
    root = get_platforms_dir(platforms_dir)
    return root / f"{platform_id}.json"


def load_platform_config(platform_id: str, platforms_dir: Optional[Path] = None) -> Optional[PlatformConfig]:
    """读取平台配置，不存在或解析失败返回 None。"""
    path = path_for_platform(platform_id, platforms_dir)
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        data.setdefault("platform", platform_id)
        return PlatformConfig.model_validate(data)
    except Exception as e:
        logger.warning("load_platform_config failed: %s path=%s", e, path)
        return None


def save_platform_config(config: PlatformConfig, platforms_dir: Optional[Path] = None) -> bool:
    """保存平台配置。"""
    path = path_for_platform(config.platform, platforms_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = config.model_dump_json(indent=2, ensure_ascii=False)
        path.write_text(raw, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning("save_platform_config failed: %s path=%s", e, path)
        return False


def delete_platform_config(platform_id: str, platforms_dir: Optional[Path] = None) -> bool:
    """删除平台配置文件。文件不存在视为成功。"""
    path = path_for_platform(platform_id, platforms_dir)
    if not path.exists():
        return True
    try:
        path.unlink()
        return True
    except Exception as e:
        logger.warning("delete_platform_config failed: %s path=%s", e, path)
        return False


def list_platform_ids(platforms_dir: Optional[Path] = None) -> list[str]:
    """列出已有配置的平台 ID（按 .json 文件名）。"""
    root = get_platforms_dir(platforms_dir)
    if not root.exists():
        return []
    ids = []
    for f in root.iterdir():
        if f.suffix.lower() == ".json" and f.stem and not f.name.endswith(".resources.json"):
            ids.append(f.stem)
    return sorted(ids)
