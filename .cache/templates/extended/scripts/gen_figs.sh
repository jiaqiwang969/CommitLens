#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
# Optional label for subdirectory under figs, e.g. NNN-<short>
LABEL="${1:-}"
if [ -n "$LABEL" ]; then
  PUML_DIR="$DIR/figs/$LABEL"
  mkdir -p "$PUML_DIR"
else
  PUML_DIR="$DIR/figs"
fi
plantuml_bin="$(command -v plantuml || true)"

if [ -n "$plantuml_bin" ]; then
  # 1) Export SVG first
  "$plantuml_bin" -tsvg -o . "$PUML_DIR"/*.puml || true
  # 2) Convert SVG -> PDF
  converted=0
  if command -v rsvg-convert >/dev/null 2>&1; then
    for s in "$PUML_DIR"/*.svg; do
      [ -f "$s" ] || continue
      rsvg-convert -f pdf -o "${s%.svg}.pdf" "$s" && converted=1
    done
  elif command -v sips >/dev/null 2>&1; then
    for s in "$PUML_DIR"/*.svg; do
      [ -f "$s" ] || continue
      sips -s format pdf "$s" --out "${s%.svg}.pdf" >/dev/null && converted=1
    done
  fi
  if [ "$converted" -eq 1 ]; then
    echo "OK: SVG generated and converted to PDF under $PUML_DIR"
  else
    echo "OK: SVG generated under $PUML_DIR (no converter found for PDF)" >&2
  fi
else
  echo "WARN: plantuml not found; please install to export SVG/PDF" >&2
fi
