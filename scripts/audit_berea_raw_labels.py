#!/usr/bin/env python3
"""Audit Berea microCT labels without modifying the original raw file."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "论文数据" / "microCT_Berea.raw"
OUT_DIR = ROOT / "outputs" / "berea_label_check"
SHAPE = (350, 350, 350)
DTYPE = "<u2"


def face_contacts(mask: np.ndarray) -> dict[str, int]:
    return {
        "x0": int(mask[0, :, :].any()),
        "x1": int(mask[-1, :, :].any()),
        "y0": int(mask[:, 0, :].any()),
        "y1": int(mask[:, -1, :].any()),
        "z0": int(mask[:, :, 0].any()),
        "z1": int(mask[:, :, -1].any()),
    }


def largest_component_fraction(mask: np.ndarray) -> tuple[int, int, float, dict[str, int]]:
    structure = ndimage.generate_binary_structure(3, 1)
    labels, n_labels = ndimage.label(mask, structure=structure)
    if n_labels == 0:
        return 0, 0, 0.0, {k: 0 for k in ("x0", "x1", "y0", "y1", "z0", "z1")}

    counts = np.bincount(labels.ravel())
    counts[0] = 0
    largest_label = int(counts.argmax())
    largest_count = int(counts[largest_label])
    frac = largest_count / float(mask.sum())
    contacts = face_contacts(labels == largest_label)
    return n_labels, largest_count, frac, contacts


def save_slice_panel(arr: np.ndarray) -> None:
    mid = arr.shape[0] // 2
    slices = {
        "x_mid": arr[mid, :, :],
        "y_mid": arr[:, mid, :],
        "z_mid": arr[:, :, mid],
    }

    fig, axes = plt.subplots(2, 3, figsize=(10, 6), constrained_layout=True)
    for col, (name, slc) in enumerate(slices.items()):
        axes[0, col].imshow(slc == 1, cmap="gray", interpolation="nearest")
        axes[0, col].set_title(f"{name}: label 1")
        axes[1, col].imshow(slc == 2, cmap="gray", interpolation="nearest")
        axes[1, col].set_title(f"{name}: label 2")
        for row in range(2):
            axes[row, col].set_xticks([])
            axes[row, col].set_yticks([])
    fig.savefig(OUT_DIR / "berea_label_center_slices.png", dpi=180)
    plt.close(fig)

    for name, slc in slices.items():
        plt.imsave(OUT_DIR / f"{name}_label1_mask.png", slc == 1, cmap="gray")
        plt.imsave(OUT_DIR / f"{name}_label2_mask.png", slc == 2, cmap="gray")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    arr = np.memmap(RAW_PATH, dtype=DTYPE, mode="r", shape=SHAPE)

    values, counts = np.unique(arr, return_counts=True)
    total = int(np.prod(SHAPE))

    rows: list[dict[str, str | int | float]] = []
    for value, count in zip(values, counts):
        mask = np.asarray(arr == value)
        n_components, largest_count, largest_frac, contacts = largest_component_fraction(mask)
        rows.append(
            {
                "label": int(value),
                "voxel_count": int(count),
                "volume_fraction": float(count / total),
                "component_count_6_connected": n_components,
                "largest_component_voxels": largest_count,
                "largest_component_fraction_of_label": largest_frac,
                "largest_component_touches_x0": contacts["x0"],
                "largest_component_touches_x1": contacts["x1"],
                "largest_component_touches_y0": contacts["y0"],
                "largest_component_touches_y1": contacts["y1"],
                "largest_component_touches_z0": contacts["z0"],
                "largest_component_touches_z1": contacts["z1"],
            }
        )

    with (OUT_DIR / "berea_label_stats.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    save_slice_panel(arr)

    print("raw_path", RAW_PATH)
    print("shape", SHAPE)
    print("dtype", DTYPE)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()

