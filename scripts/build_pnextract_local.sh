#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pnextract_root="$project_root/pnextract"

mkdir -p "$pnextract_root/build/local" "$pnextract_root/bin"

/usr/bin/g++ -std=c++17 -O2 -Wall -pedantic \
  -DRELEASE_DATE='"2026.05.20-local"' \
  -D_FILE_OFFSET_BITS=64 \
  -I"$pnextract_root/src/include" \
  -I"$pnextract_root/src/libvoxel" \
  -I"$pnextract_root/src/pnm/pnextract" \
  "$pnextract_root/src/pnm/pnextract/blockNet.cpp" \
  "$pnextract_root/src/pnm/pnextract/nextract.cpp" \
  "$pnextract_root/src/pnm/pnextract/medialSurf.cpp" \
  "$pnextract_root/src/pnm/pnextract/writers_vtk.cpp" \
  "$pnextract_root/src/pnm/pnextract/writers_vxl.cpp" \
  "$pnextract_root/src/libvoxel/voxelImage.cpp" \
  -o "$pnextract_root/build/local/pnextract"

cp "$pnextract_root/build/local/pnextract" "$pnextract_root/bin/pnextract"
chmod +x "$pnextract_root/bin/pnextract"

"$pnextract_root/bin/pnextract" -h

