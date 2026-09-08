#!/usr/bin/env sh
# 개발 서버. 포트는 7999 로 고정한다 — uvicorn 기본값은 8000 이라
# --port 를 잊으면 조용히 다른 포트로 뜬다.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/uvicorn app.main:app --port 7999 "$@"
