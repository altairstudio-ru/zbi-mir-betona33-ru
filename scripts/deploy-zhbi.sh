#!/bin/bash
# deploy-zhbi.sh — выгрузка dist/ + обработчика заявок на TimeWeb-хостинг по FTP
cd "$(dirname "$0")/.." || exit 1
U="ftp://5.23.50.56"
F="$U/zhbi.mir-betona33.ru/public_html"
CREDS="$(sed -n '1p' /c/Users/Andrey/.qoder-tmp-ssh/.creds.txt):$(sed -n '2p' /c/Users/Andrey/.qoder-tmp-ssh/.creds.txt)"
BK="/c/Users/Andrey/.qoder-tmp-ssh/backup"
mkdir -p "$BK"

ftp_put() { # local remote
  for i in 1 2 3; do
    curl -sS --ftp-create-dirs --retry 2 -m 180 -T "$1" "$2" --user "$CREDS" && return 0
    sleep 2
  done
  echo "FAIL: $1"; return 1
}

echo "== 1. бэкап заглушки =="
curl -sS -m 30 "$F/index.htm" --user "$CREDS" -o "$BK/zhbi-index.htm.$(date +%F)" || echo "(заглушку не скачал — возможно, уже удалена)"
curl -sS -m 30 "$F/index.htm" --user "$CREDS" -Q "-RENAME index.htm _backup-index.htm" -o /dev/null && echo "на сервере: index.htm -> _backup-index.htm"

echo "== 2. выгрузка dist/ =="
n=0; fail=0
while IFS= read -r f; do
  rel="${f#dist/}"
  if ftp_put "$f" "$F/$rel"; then n=$((n+1)); else fail=1; fi
done < <(find dist -type f)
echo "файлов загружено: $n"; [ $fail -eq 0 ] && echo "все ОК" || echo "ЕСТЬ ОШИБКИ"

echo "== 3. обработчик заявок =="
ftp_put server/lead.php "$F/api/lead/index.php" && echo "lead.php -> /api/lead/index.php"

echo "== 4. чистка пробников =="
for p in probe.php probe2.php api-lead-test.php; do
  curl -sS -m 20 "$F/$p" --user "$CREDS" -Q "-DELE $p" -o /dev/null 2>/dev/null && echo "удалён $p" || true
done
echo DONE
