#!/usr/bin/env python3
"""Parse pnextract Statoil-style node/link files into CSV summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def read_node2(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            rows.append(
                {
                    "pore_id": int(parts[0]),
                    "pore_volume_m3": float(parts[1]),
                    "pore_radius_m": float(parts[2]),
                    "pore_shape_factor": float(parts[3]),
                    "pore_clay_volume": float(parts[4]),
                }
            )
    return pd.DataFrame(rows)


def read_link1(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        first = True
        for line in f:
            if first:
                first = False
                continue
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) < 6:
                continue
            rows.append(
                {
                    "throat_id": int(parts[0]),
                    "pore1_id": int(parts[1]),
                    "pore2_id": int(parts[2]),
                    "throat_radius_m": float(parts[3]),
                    "throat_shape_factor": float(parts[4]),
                    "pore_center_to_center_length_m": float(parts[5]),
                }
            )
    return pd.DataFrame(rows)


def read_link2(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) < 8:
                continue
            rows.append(
                {
                    "throat_id": int(parts[0]),
                    "pore1_id_link2": int(parts[1]),
                    "pore2_id_link2": int(parts[2]),
                    "pore1_length_m": float(parts[3]),
                    "pore2_length_m": float(parts[4]),
                    "throat_length_m": float(parts[5]),
                    "throat_volume_m3": float(parts[6]),
                    "throat_clay_volume": float(parts[7]),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, help="pnextract output prefix, e.g. path/Berea350_full")
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    prefix = Path(args.prefix)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    pores = read_node2(prefix.with_name(prefix.name + "_node2.dat"))
    link1 = read_link1(prefix.with_name(prefix.name + "_link1.dat"))
    link2 = read_link2(prefix.with_name(prefix.name + "_link2.dat"))
    throats = link1.merge(link2, on="throat_id", how="inner")

    pores.to_csv(outdir / "pores.csv", index=False)
    throats.to_csv(outdir / "throats.csv", index=False)

    summary = {
        "prefix": str(prefix),
        "n_pores": int(len(pores)),
        "n_throats": int(len(throats)),
        "pore_radius_volume_weighted_mean_m": float(np.average(pores["pore_radius_m"], weights=pores["pore_volume_m3"])),
        "throat_length_volume_weighted_mean_m": float(np.average(throats["throat_length_m"], weights=throats["throat_volume_m3"])),
        "pore_radius_min_m": float(pores["pore_radius_m"].min()),
        "pore_radius_max_m": float(pores["pore_radius_m"].max()),
        "throat_length_min_m": float(throats["throat_length_m"].min()),
        "throat_length_max_m": float(throats["throat_length_m"].max()),
    }
    (outdir / "network_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

