#!/usr/bin/env bash
set -euo pipefail
BASE="http://127.0.0.1:5000"
RED=$'\e[31m'; GRN=$'\e[32m'; YLW=$'\e[33m'; RST=$'\e[0m'
pass(){ echo "${GRN}PASS${RST} - $*"; }
fail(){ echo "${RED}FAIL${RST} - $*"; exit 1; }

# 0) porta 5000 escutando?
if ss -ltnp | grep -q ':5000 '; then pass "porta 5000 escutando"; else fail "porta 5000 não está escutando"; fi

# 1) /healthz 200 e JSON com status ok
code=$(curl -s -o /tmp/hz.json -w "%{http_code}" "$BASE/healthz" || true)
jqok=$(grep -o '"status":"ok"' /tmp/hz.json || true)
[[ "$code" == "200" && -n "$jqok" ]] && pass "/healthz responde 200 e status ok" || fail "/healthz não respondeu ok (code=$code, body=$(cat /tmp/hz.json))"

# 2) / (home) retorna HTML
code=$(curl -s -o /tmp/home.html -w "%{http_code}" "$BASE/" || true)
grep -qi '<html' /tmp/home.html && [[ "$code" == "200" ]] && pass "/ (home) HTML 200" || fail "/ (home) não retornou HTML 200 (code=$code)"

# 3) /splits retorna HTML com tabela
code=$(curl -s -o /tmp/splits.html -w "%{http_code}" "$BASE/splits" || true)
if [[ "$code" == "200" ]] && grep -qiE '<table|<tr|<td' /tmp/splits.html; then
  pass "/splits HTML 200"
else
  fail "/splits não retornou HTML/tabela 200 (code=$code)"
fi

# 4) detalhe de um split (pega o maior ID existente; se não houver, pula)
if command -v sqlite3 >/dev/null 2>&1 && [[ -f guild_ledger.db ]]; then
  sid=$(sqlite3 guild_ledger.db 'SELECT id FROM splits ORDER BY id DESC LIMIT 1;' 2>/dev/null || true)
  if [[ -n "$sid" ]]; then
    code=$(curl -s -o /tmp/split.html -w "%{http_code}" "$BASE/splits/$sid" || true)
    [[ "$code" == "200" ]] && grep -qi '<html' /tmp/split.html && pass "/splits/$sid HTML 200" || fail "/splits/$sid não retornou HTML 200 (code=$code)"
  else
    echo "${YLW}SKIP${RST} - nenhum split na base para testar detalhe"
  fi
else
  echo "${YLW}SKIP${RST} - sqlite3 não disponível ou sem guild_ledger.db para testar detalhe do split"
fi

echo
echo "Resumo: ${GRN}todos os testes essenciais passaram${RST} ✅"
