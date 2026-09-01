#!/usr/bin/env bash
# Prueba de validez del endpoint S3 del cliente (RF-03).
# Lee S3_UPLOAD_API_URL y S3_UPLOAD_API_KEY del .env — la API key NUNCA se imprime.
# Uso:  ./probar-url-s3.sh
set -euo pipefail
cd "$(dirname "$0")"

# Tomar los valores del .env (incluso si están comentados con #).
URL=$(grep -E '^[# ]*S3_UPLOAD_API_URL=' .env | tail -1 | sed 's/^[# ]*S3_UPLOAD_API_URL=//' | tr -d '"'"'"' \r')
KEY=$(grep -E '^[# ]*S3_UPLOAD_API_KEY=' .env | tail -1 | sed 's/^[# ]*S3_UPLOAD_API_KEY=//' | tr -d '"'"'"' \r')
HOST=$(printf '%s' "$URL" | sed -E 's#https?://([^/]+)/?.*#\1#')

echo "URL a probar: $URL"
echo "API key     : $([ -n "$KEY" ] && echo 'cargada (oculta)' || echo 'VACÍA')"
echo

echo "== 1) DNS =="
if getent hosts "$HOST" >/dev/null 2>&1; then
  echo "   OK  el dominio existe"
else
  echo "   FALLA  NXDOMAIN — el dominio no existe. La URL no es valida. (para aqui)"
  exit 1
fi

echo "== 2) Conexion HTTPS =="
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL" || true)
echo "   HTTP $code (cualquier respuesta != 000 = conecta)"

echo "== 3) POST real con la key =="
code=$(curl -s -o /tmp/s3test.out -w '%{http_code}' --max-time 30 -X POST "$URL" \
  -H "Content-Type: application/json" -H "x-api-key: $KEY" \
  --data '{"file":"dGVzdA==","filename":"prueba","path":"abacusplus/documentos/ikbo/"}' || true)
echo "   HTTP $code"
echo "   Respuesta:"; sed 's/^/     /' /tmp/s3test.out; echo
case "$code" in
  200) echo ">> URL VALIDA Y FUNCIONANDO. Puedes conectar Abacus.";;
  401|403) echo ">> La URL vive, pero revisar la API key / header.";;
  *)   echo ">> Revisar: la URL no respondio correctamente.";;
esac
