#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
kicad_cli="${KICAD_CLI:-/mnt/c/Program Files/KiCad/10.0/bin/kicad-cli.exe}"
board="esp32c6-solar-controller.kicad_pcb"
schematic="esp32c6-solar-controller.kicad_sch"

cd "$root"

mkdir -p \
  exports/fabrication \
  exports/assembly \
  exports/mechanical \
  exports/review

python3 tools/validate_hardware_contract.py

"$kicad_cli" pcb drc \
  --format json \
  --output exports/drc-final.json \
  --severity-all \
  --all-track-errors \
  "$board"

"$kicad_cli" sch erc \
  --format json \
  --output exports/erc-final.json \
  --severity-all \
  "$schematic"

"$kicad_cli" sch export netlist \
  --format kicadxml \
  --output exports/esp32c6-solar-controller.net.xml \
  "$schematic"

python3 tools/validate_netlist.py

"$kicad_cli" pcb export gerbers \
  --output exports/fabrication \
  --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts \
  --subtract-soldermask \
  --precision 6 \
  --use-drill-file-origin \
  --check-zones \
  "$board"

"$kicad_cli" pcb export drill \
  --output exports/fabrication \
  --format excellon \
  --drill-origin plot \
  --excellon-units mm \
  --excellon-separate-th \
  --generate-map \
  --map-format pdf \
  --generate-report \
  --report-path exports/fabrication/drill-report.txt \
  "$board"

"$kicad_cli" pcb export pos \
  --output exports/assembly/kicad-smt-top.csv \
  --side front \
  --format csv \
  --units mm \
  --smd-only \
  --exclude-dnp \
  --use-drill-file-origin \
  "$board"

python3 tools/generate_order_files.py
python3 tools/generate_enclosure_cad.py

"$kicad_cli" sch export pdf \
  --output exports/esp32c6-solar-controller.pdf \
  "$schematic"

if command -v mutool >/dev/null 2>&1; then
  mutool draw \
    -q \
    -r 120 \
    -o exports/review/schematic-a1-layout.png \
    exports/esp32c6-solar-controller.pdf \
    1
fi

"$kicad_cli" pcb export pdf \
  --output exports/assembly/top-assembly.pdf \
  --mode-single \
  --layers F.Fab,F.Silkscreen,Edge.Cuts \
  --exclude-value \
  --sketch-pads-on-fab-layers \
  --check-zones \
  "$board"

"$kicad_cli" pcb export step \
  --output exports/mechanical/controller-board-only-rev-a.step \
  --force \
  --board-only \
  --cut-vias-in-body \
  "$board"

"$kicad_cli" pcb render \
  --output exports/review/pcb-top.png \
  --width 2400 \
  --height 1600 \
  --side top \
  --quality high \
  --background opaque \
  "$board"

"$kicad_cli" pcb render \
  --output exports/review/pcb-isometric.png \
  --width 2400 \
  --height 1600 \
  --side top \
  --quality high \
  --background opaque \
  --perspective \
  --floor \
  --rotate 325,0,35 \
  "$board"

zip -j -FS exports/esp32c6-solar-controller-rev-a-gerbers.zip \
  exports/fabrication/*.gtl \
  exports/fabrication/*.g1 \
  exports/fabrication/*.g2 \
  exports/fabrication/*.gbl \
  exports/fabrication/*.gtp \
  exports/fabrication/*.gto \
  exports/fabrication/*.gbo \
  exports/fabrication/*.gts \
  exports/fabrication/*.gbs \
  exports/fabrication/*.gm1 \
  exports/fabrication/*.drl

echo "Rev A release outputs exported under $root/exports"
