#!/usr/bin/env bash
# One-command reproduction: download data, run every platform, generate RESULTS.md
set -euo pipefail
cd "$(dirname "$0")/.."

python -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f data/raw/edges.csv ]; then
  python data/download_dataset.py --dataset email-enron
fi

python run_benchmark.py --platform all --step all --concurrency 1 10 40

python -m harness.report --input results/ --output RESULTS.md

echo "Done. See RESULTS.md"
