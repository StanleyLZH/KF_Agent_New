# 客服软件操控服务

在服务器上运行，通过 HTTP API 控制多款客服软件（千牛、小红书、抖音等）的打开、登录、上线与下线、关闭。流程与按钮通过 JSON 配置，支持可视化流程编辑器。

## 环境

- Python 3.10+
- 建议部署在 **Windows** 机器上（客服端多为 Windows 桌面应用）；非 Windows 下仅支持图像/坐标驱动，无 pywinauto 窗口等待/关窗。

## 安装与运行

### 从私有 PyPI 安装（推荐，用于其他服务器）

配置 pip 使用你的私有仓库后：

```bash
pip install kf-agent
```

启动服务：

```bash
kf-agent
```

默认监听 `0.0.0.0:8000`。可通过环境变量或当前目录下的 `.env` 覆盖 `host`、`port`、`log_level`。  
**平台配置目录**：默认使用当前工作目录下的 `platforms/`。若需指定目录，设置环境变量：

```bash
export KF_AGENT_PLATFORMS_DIR=/path/to/platforms
kf-agent
```

### 从源码安装（开发或自建包）

```bash
pip install -e .
# 可选：下载文档静态资源到 kf_agent/static（若缺失）
python scripts/download_docs_assets.py
```

启动方式任选其一：

```bash
kf-agent
# 或
uvicorn main:app --host 0.0.0.0 --port 8000
```

（从项目根目录运行 `uvicorn main:app` 时需已执行 `pip install -e .`）

## API

- `POST /customer_service/open` — 打开并上线：Body `{"platform": "qianniu"}`
- `POST /customer_service/close` — 下线并关闭：Body `{"platform": "qianniu"}`
- `GET /customer_service/status?platform=qianniu` — 查询状态
- `GET /customer_service/platforms` — 已配置平台列表
- `GET /config/platforms/{platform}` — 获取某平台配置
- `PUT /config/platforms/{platform}` — 更新某平台配置（打开/关闭步骤、display_name）

## 配置

各平台配置放在 `platforms/{平台ID}.json`，例如 `platforms/qianniu.json`。结构包括：

- `platform`: 平台 ID
- `display_name`: 展示名称（可选）
- `open`: 打开并上线步骤数组
- `close`: 下线并关闭步骤数组

步骤类型：`launch`、`wait_window`、`click`、`input_text`、`wait`、`hotkey`、`close_window`。  
点击步骤的 `element` 支持：坐标 `coord`、图像模板 `image`（文件名放在 `platforms/templates/`）、控件 `control`（需 Windows 驱动支持）。

将各平台按钮截图放到 `platforms/templates/`，在配置里用文件名引用即可（如 `qianniu_online_btn.png`）。可先手改 JSON 或通过 `PUT /config/platforms/{platform}` 更新，后续可做可视化配置界面。

## 发布到私有 PyPI

### 方式一：快捷键（推荐）

1. 在项目根目录创建 `.env.pypi`（可复制 `.env.pypi.example`），填写：
   - `PYPI_REPO_URL`：私有 PyPI 地址，如 `https://你的仓库/simple/`
   - 可选：`PYPI_USERNAME`、`PYPI_PASSWORD`（否则上传时 twine 会提示输入）
2. 安装依赖：`pip install build twine`
3. 在 Cursor/VS Code 中按 **Ctrl+Shift+U**（Mac 可用 Cmd+Shift+U，若冲突可在快捷键设置中将「Run Task」绑到该任务），即可执行「构建并上传到私有 PyPI」任务。

任务定义在 `.vscode/tasks.json`，快捷键在 `.vscode/keybindings.json`。

### 方式二：命令行

```bash
pip install build twine
# 设置私有仓库地址（或写在 .env.pypi）
export PYPI_REPO_URL=https://你的私有仓库地址/simple/
python scripts/publish_to_pypi.py
```

其他机器配置该私有源后即可 `pip install kf-agent` 并执行 `kf-agent`。

## 目录结构

```
├── pyproject.toml       # 包配置与依赖
├── main.py              # 开发时 uvicorn main:app 入口（导入 kf_agent）
├── kf_agent/            # 主包（pip 安装后由 kf-agent 命令启动）
│   ├── main.py          # FastAPI 应用与 run() 入口
│   ├── static/          # 文档与流程编辑器静态资源
│   ├── config/          # 全局配置
│   ├── api/routes/      # HTTP 接口
│   ├── core/             # 流程引擎与模型
│   ├── drivers/          # UI 驱动
│   └── storage/          # 平台配置读写
├── scripts/             # 工具脚本（如 download_docs_assets.py）
└── platforms/           # 各平台 JSON + templates/（开发或通过 KF_AGENT_PLATFORMS_DIR 指定）
```
