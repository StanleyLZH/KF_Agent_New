"""开发时从项目根运行 uvicorn main:app 时使用（需先 pip install -e .）。"""
from kf_agent.main import app

__all__ = ["app"]
