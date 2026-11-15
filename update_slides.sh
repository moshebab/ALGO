#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")"

if [[ $# -gt 0 ]]; then
  python3 publish_lectures.py --add "$@"
else
  python3 publish_lectures.py
fi

git add -A
if git diff --cached --quiet; then
  echo "No changes to publish."
else
  git commit -m "Update published ALGO lecture slides"
  git push -u origin main
  echo "Published to https://moshebab.github.io/ALGO/"
fi
