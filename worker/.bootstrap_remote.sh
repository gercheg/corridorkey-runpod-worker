set -euo pipefail
echo '--- nvidia-smi ---'
nvidia-smi || true
echo '--- python ---'
python --version || true
python3 --version || true
echo '--- disk ---'
df -h /workspace
echo '--- step 4b install uv ---'
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
uv --version
echo '--- step 4c clone CorridorKey ---'
mkdir -p /workspace && cd /workspace
if [ ! -d CorridorKey ]; then
  git clone https://github.com/nikopueringer/CorridorKey.git
fi
cd CorridorKey
git rev-parse HEAD | tee /workspace/CORRIDORKEY_COMMIT
ls -la