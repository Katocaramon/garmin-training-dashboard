#!/bin/bash
# Doppio clic: avvia il server locale (se non e' gia' attivo) e apre la dashboard.
cd "$(dirname "$0")" || exit 1
if ! curl -s -o /dev/null http://127.0.0.1:8765/ping; then
  nohup python3 serve.py > /dev/null 2>&1 &
  for i in 1 2 3 4 5 6 7 8 9 10; do curl -s -o /dev/null http://127.0.0.1:8765/ping && break; sleep 0.3; done
fi
open http://127.0.0.1:8765/
