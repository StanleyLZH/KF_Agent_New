"""全局配置：端口、日志、平台配置目录等。"""
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_platforms_dir() -> Path:
    """优先使用环境变量 KF_AGENT_PLATFORMS_DIR，否则使用当前工作目录下的 platforms。"""
    env = os.environ.get("KF_AGENT_PLATFORMS_DIR")
    if env:
        return Path(env)
    return Path.cwd() / "platforms"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 服务
    host: str = "0.0.0.0"
    port: int = 8000

    # 平台配置目录（可通过环境变量 KF_AGENT_PLATFORMS_DIR 覆盖）
    platforms_dir: Path = Field(default_factory=_default_platforms_dir)
    templates_dir_name: str = "templates"

    # 日志
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
