#!/bin/bash
# 构建并通过 SCP 上传到服务器目录（与另一项目一致，不走 PyPI HTTP 上传）
# 配置从项目根目录 .env.pypi 读取：REMOTE_HOST, REMOTE_USER, REMOTE_PASSWORD, REMOTE_PORT, REMOTE_DIR

set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# 加载 .env.pypi 中的 REMOTE_* 变量
if [ -f .env.pypi ]; then
  set -a
  while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    if [[ "$line" =~ ^REMOTE_[A-Z_]+= ]]; then
      export "$line"
    fi
  done < .env.pypi
  set +a
fi

# 默认值（可被 .env.pypi 覆盖）
REMOTE_HOST="${REMOTE_HOST:-45.40.244.153}"
REMOTE_USER="${REMOTE_USER:-developer_user}"
REMOTE_PASSWORD="${REMOTE_PASSWORD:-}"
REMOTE_PORT="${REMOTE_PORT:-22}"
REMOTE_DIR="${REMOTE_DIR:-c:/WhisperPackages}"
DIST_DIR="$ROOT/dist"

# 检查必要配置
if [ -z "$REMOTE_PASSWORD" ]; then
  echo "❌ REMOTE_PASSWORD 未设置，请在 .env.pypi 中填写 REMOTE_PASSWORD=..."
  exit 1
fi

# 激活虚拟环境并构建
if [ -d ".venv" ]; then
  source ./.venv/bin/activate
elif [ -d "venv" ]; then
  source ./venv/bin/activate
fi

echo "Building..."
python -m build
if [ $? -ne 0 ]; then
  echo "❌ Build failed."
  exit 1
fi

# 检查 dist 目录
if [ ! -d "$DIST_DIR" ]; then
  echo "❌ dist directory not found."
  exit 1
fi

FILES=$(find "$DIST_DIR" -type f \( -name "*.whl" -o -name "*.tar.gz" \) 2>/dev/null)
if [ -z "$FILES" ]; then
  echo "⚠️  No .whl or .tar.gz files in dist/. Nothing to upload."
  exit 0
fi

echo "🚀 Uploading to $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
echo "$FILES"
echo

# 检查 sshpass
if ! command -v sshpass &> /dev/null; then
  echo "❌ sshpass not found. Install: brew install sshpass (macOS) or apt install sshpass (Linux)"
  exit 1
fi

for file in $FILES; do
  filename=$(basename "$file")
  # 检查远程是否已存在（PowerShell 在 Windows 服务器上检查）
  check_cmd="powershell -Command \"if (Test-Path '$REMOTE_DIR\\$filename') { Write-Output '[EXIST]' }\""
  check_result=$(sshpass -p "$REMOTE_PASSWORD" ssh -p "$REMOTE_PORT" -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "$check_cmd" 2>/dev/null || true)

  if [[ "$check_result" == *"[EXIST]"* ]]; then
    echo "⏭️  Skipping $filename (already exists)"
  else
    echo "📤 Uploading $filename..."
    if sshpass -p "$REMOTE_PASSWORD" scp -P "$REMOTE_PORT" -o StrictHostKeyChecking=no "$file" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"; then
      echo "✅ $filename uploaded."
    else
      echo "❌ Failed to upload $filename"
      exit 1
    fi
  fi
done

echo ""
echo "✅ Done."
