#!/usr/bin/env bash
# 稳健分段下载 v2：每段独立 curl -L，校验 HTTP 206 + size_download 精确，写固定偏移。
# 用法: fetch_parts.sh <url> <out> <size> <threads> <magic_hex>
set -u
URL="$1"; OUT="$2"; SIZE="$3"; N="${4:-8}"; MAGIC="${5:-}"
PARTS="${OUT}.parts"
mkdir -p "$PARTS"
CHUNK=$(( (SIZE + N - 1) / N ))
seg() {
  i=$1; START=$(( i * CHUNK )); END=$(( START + CHUNK - 1 ))
  [ $END -ge $SIZE ] && END=$(( SIZE - 1 ))
  EXP=$(( END - START + 1 ))
  P="$PARTS/p$(printf %02d $i).bin"
  for try in $(seq 1 40); do
    rm -f "$P"
    CODE=$(curl -sS -L --connect-timeout 20 --max-time 1800 \
      -H "Accept-Encoding: identity" -r ${START}-${END} \
      -o "$P" -w '%{http_code} %{size_download}' "$URL" 2>/dev/null)
    HC=${CODE%% *}; GOT=${CODE##* }
    if [ "$HC" = "206" ] && [ "$GOT" = "$EXP" ]; then
      echo "seg$i OK $EXP"; return 0
    fi
    echo "seg$i retry try=$try http=$HC got=$GOT exp=$EXP"
    sleep $(( 2 + try / 3 ))
  done
  echo "seg$i FAIL"; return 1
}
export -f seg 2>/dev/null || true
PIDS=""
for i in $(seq 0 $((N-1))); do
  ( seg $i ) &
  PIDS="$PIDS $!"
  sleep 0.5
done
FAIL=0
for p in $PIDS; do wait $p || FAIL=1; done
if [ $FAIL -ne 0 ]; then echo "SOME_SEG_FAILED"; exit 1; fi
: > "$OUT"
for i in $(seq 0 $((N-1))); do cat "$PARTS/p$(printf %02d $i).bin" >> "$OUT"; done
ACT=$(stat -c %s "$OUT")
echo "final $ACT/$SIZE"
if [ "$ACT" -ne "$SIZE" ]; then echo SIZE_MISMATCH; exit 1; fi
if [ -n "$MAGIC" ]; then
  HEAD=$(head -c 4 "$OUT" | od -An -tx1 | tr -d ' \n')
  echo "magic=$HEAD exp=$MAGIC"
  [ "$HEAD" = "$MAGIC" ] || { echo MAGIC_BAD; exit 1; }
fi
echo ALL_OK
rm -rf "$PARTS"
