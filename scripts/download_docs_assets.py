"""一次性下载 Swagger UI / ReDoc 静态资源到 static/，供本地 /docs 使用（Chrome/Cursor 不依赖外网 CDN）。"""
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
# 写入包内 static，供安装后 /docs 使用
STATIC = BASE / "kf_agent" / "static"
# 每个文件可配置多个 CDN，依次尝试
ASSETS = [
    (
        "swagger-ui-bundle.js",
        [
            "https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
            "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        ],
    ),
    (
        "swagger-ui.css",
        [
            "https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
            "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        ],
    ),
    (
        "redoc.standalone.js",
        [
            "https://unpkg.com/redoc@2/bundles/redoc.standalone.js",
            "https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js",
        ],
    ),
]


def main():
    STATIC.mkdir(parents=True, exist_ok=True)
    for name, urls in ASSETS:
        path = STATIC / name
        if path.exists() and path.stat().st_size > 1000:
            print(f"skip (exists): {name}")
            continue
        print(f"downloading: {name} ...")
        ok = False
        for url in urls:
            try:
                urllib.request.urlretrieve(url, path)
                if path.stat().st_size > 1000:
                    print(f"ok: {name}")
                    ok = True
                    break
            except Exception as e:
                print(f"  try {url[:40]}... fail: {e}")
        if not ok:
            print(f"fail (all sources): {name}")


if __name__ == "__main__":
    main()
