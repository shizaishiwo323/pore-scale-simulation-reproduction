#!/usr/bin/env python3
"""Prepare uint8 pnextract input from the original Berea uint16 raw file."""

from __future__ import annotations

from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "论文数据" / "microCT_Berea.raw"
OUT_DIR = ROOT / "experiments" / "berea_pnextract"
OUT_RAW = OUT_DIR / "Berea350_pore0_solid1.raw"
SHAPE = (350, 350, 350)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    src = np.memmap(RAW_PATH, dtype="<u2", mode="r", shape=SHAPE)
    dst = np.memmap(OUT_RAW, dtype="u1", mode="w+", shape=SHAPE)

    # Label audit supports 1 = pore/water, 2 = solid. pnextract expects pore as 0.
    dst[:] = np.where(src == 1, 0, 1).astype("u1")
    dst.flush()

    values, counts = np.unique(dst, return_counts=True)
    print("wrote", OUT_RAW)
    print("bytes", OUT_RAW.stat().st_size)
    for value, count in zip(values, counts):
        print(int(value), int(count), float(count / dst.size))


if __name__ == "__main__":
    main()

