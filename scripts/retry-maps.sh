#!/bin/bash
# retry-maps.sh — долбить Overpass, пока не построятся kovrov и yuryev-polsky
cd "$(dirname "$0")/.." || exit 1
for round in $(seq 1 12); do
  ok=1
  for city in yuryev-polsky kovrov; do
    if [ ! -f "public/delivery/$city.json" ]; then
      echo "=== round $round: build $city $(date +%H:%M) ==="
      python scripts/gen_delivery_data.py --city "$city" 2>&1 | tail -6
    fi
  done
  [ -f public/delivery/kovrov.json ] && [ -f public/delivery/yuryev-polsky.json ] && { echo "BOTH DONE"; exit 0; }
  sleep 1200
done
echo "TIMEOUT: not all maps built"
ls -la public/delivery/
