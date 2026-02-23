#!/usr/bin/env python3
"""
构建项目并上传到私有 PyPI。

使用前请在项目根目录 .env.pypi 中配置：
  PYPI_REPO_URL   pip 安装用的索引地址，例如 http://host/WhisperPackages/simple/
  PYPI_UPLOAD_URL 上传用的地址（可选）。若与安装地址不同则必填，例如 http://host/WhisperPackages/ 或 .../legacy/
  PYPI_USERNAME   上传用户名（可选）
  PYPI_PASSWORD   上传密码（可选）
  PYPI_USE_HTTP   设为 1 时强制用 HTTP 代替 HTTPS

404=上传路径不对。405=/simple/ 仅用于安装。403=认证或权限不足，请核对 PYPI_USERNAME/PYPI_PASSWORD 及该用户在仓库的上传/部署权限。
"""
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent


def load_dotenv_pypi() -> None:
    """若存在 .env.pypi 则加载到 os.environ。"""
    env_file = ROOT / ".env.pypi"
    if not env_file.exists():
        return
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    os.chdir(ROOT)
    load_dotenv_pypi()

    repo_url = os.environ.get("PYPI_REPO_URL")
    if not repo_url:
        print("请在项目根目录创建 .env.pypi 并填写 PYPI_REPO_URL=你的私有PyPI地址", file=sys.stderr)
        return 1

    repo_url = repo_url.strip().rstrip("/") + "/"
    if os.environ.get("PYPI_USE_HTTP", "").strip() == "1":
        parsed = urlparse(repo_url)
        if parsed.scheme == "https":
            repo_url = urlunparse(("http", parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
            print("已按 PYPI_USE_HTTP=1 使用 HTTP:", repo_url)

    # 上传地址：若配置了 PYPI_UPLOAD_URL 则用其上传，否则用 PYPI_REPO_URL（部分服务器安装与上传同地址）
    upload_url = os.environ.get("PYPI_UPLOAD_URL", "").strip().rstrip("/")
    if upload_url:
        upload_url = upload_url + "/"
        if os.environ.get("PYPI_USE_HTTP", "").strip() == "1":
            parsed = urlparse(upload_url)
            if parsed.scheme == "https":
                upload_url = urlunparse(("http", parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    else:
        upload_url = repo_url

    # 清理旧构建
    for d in ["dist", "build"]:
        dpath = ROOT / d
        if dpath.exists():
            import shutil
            shutil.rmtree(dpath)
    egg = ROOT / "kf_agent.egg-info"
    if egg.exists():
        import shutil
        shutil.rmtree(egg)

    # 构建
    print("Building...")
    r = subprocess.run([sys.executable, "-m", "build"], cwd=ROOT)
    if r.returncode != 0:
        return r.returncode

    # 上传
    cmd = [
        sys.executable, "-m", "twine", "upload",
        "--repository-url", upload_url,
        "dist/*",
    ]
    if os.environ.get("PYPI_USERNAME"):
        cmd.extend(["-u", os.environ["PYPI_USERNAME"]])
    if os.environ.get("PYPI_PASSWORD"):
        cmd.extend(["-p", os.environ["PYPI_PASSWORD"]])

    print("Uploading to", upload_url, "...")
    r = subprocess.run(cmd, cwd=ROOT)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
