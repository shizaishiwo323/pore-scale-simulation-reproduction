#!/usr/bin/env python3
"""Run a small AC3D-style complex conductivity frequency sweep."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pore_scale_electrical.ac3d_solver import phase_conductivity_grid, solve_ac3d  # noqa: E402
from pore_scale_electrical.polarization import PolarizationParameters  # noqa: E402


def parse_int3(values: list[str], name: str) -> tuple[int, int, int]:
    if len(values) != 3:
        raise ValueError(f"{name} expects exactly three integers")
    parsed = tuple(int(v) for v in values)
    if any(v < 0 for v in parsed):
        raise ValueError(f"{name} must be non-negative")
    return parsed


def read_berea_subvolume(raw_path: Path, shape: tuple[int, int, int], start: tuple[int, int, int], size: tuple[int, int, int]) -> np.ndarray:
    if any(n <= 0 for n in shape) or any(n <= 0 for n in size):
        raise ValueError("shape and size entries must be positive")
    stop = tuple(s + n for s, n in zip(start, size))
    if any(e > full for e, full in zip(stop, shape)):
        raise ValueError(f"requested subvolume {start}:{stop} exceeds shape {shape}")
    volume = np.memmap(raw_path, dtype="<u2", mode="r", shape=shape, order="C")
    selection = tuple(slice(s, e) for s, e in zip(start, stop))
    return np.asarray(volume[selection])


def load_spectra(path: Path) -> pd.DataFrame:
    spectra = pd.read_csv(path)
    required = {"frequency_hz", "apparent_water_sigma_real_s_m", "apparent_water_sigma_imag_s_m"}
    missing = required.difference(spectra.columns)
    if missing:
        raise ValueError(f"spectra file is missing columns: {sorted(missing)}")
    return spectra


def nearest_spectrum_row(spectra: pd.DataFrame, frequency_hz: float) -> pd.Series:
    idx = np.abs(np.log(spectra["frequency_hz"].to_numpy(dtype=float)) - np.log(frequency_hz)).argmin()
    return spectra.iloc[int(idx)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=str(ROOT / "论文数据" / "microCT_Berea.raw"))
    parser.add_argument("--shape", nargs=3, default=("350", "350", "350"))
    parser.add_argument("--crop-start", nargs=3, default=("169", "169", "169"))
    parser.add_argument("--crop-size", nargs=3, default=("12", "12", "12"))
    parser.add_argument("--pore-label", type=int, default=1)
    parser.add_argument("--solid-label", type=int, default=2)
    parser.add_argument("--voxel-size-m", type=float, default=2.8e-6)
    parser.add_argument("--spectra", default=str(ROOT / "outputs" / "polarization_spectra_from_pnextract.csv"))
    parser.add_argument("--frequencies", nargs="+", type=float, default=[1.0e-3, 1.0, 1.0e3])
    parser.add_argument("--directions", nargs="+", choices=["x", "y", "z"], default=["x", "y", "z"])
    parser.add_argument("--out-dir", default=str(ROOT / "outputs" / "ac3d_small_grid_validation"))
    args = parser.parse_args()

    shape = parse_int3(args.shape, "--shape")
    start = parse_int3(args.crop_start, "--crop-start")
    size = parse_int3(args.crop_size, "--crop-size")
    params = PolarizationParameters()

    labels = read_berea_subvolume(Path(args.raw), shape, start, size)
    unique_labels, label_counts = np.unique(labels, return_counts=True)
    label_count_map = {int(label): int(count) for label, count in zip(unique_labels, label_counts)}
    spectra = load_spectra(Path(args.spectra))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for frequency in args.frequencies:
        spectrum_row = nearest_spectrum_row(spectra, frequency)
        used_frequency = float(spectrum_row["frequency_hz"])
        omega = 2.0 * np.pi * used_frequency
        water_sigma = complex(
            float(spectrum_row["apparent_water_sigma_real_s_m"]),
            float(spectrum_row["apparent_water_sigma_imag_s_m"]),
        )
        solid_sigma = 1j * omega * params.solid_permittivity_f_m
        sigma_grid = phase_conductivity_grid(labels, args.pore_label, args.solid_label, water_sigma, solid_sigma)

        for direction in args.directions:
            result = solve_ac3d(sigma_grid, direction=direction, voxel_size_m=args.voxel_size_m)
            rows.append(
                {
                    "requested_frequency_hz": frequency,
                    "frequency_hz": used_frequency,
                    "direction": direction,
                    "water_sigma_real_s_m": water_sigma.real,
                    "water_sigma_imag_s_m": water_sigma.imag,
                    "solid_sigma_real_s_m": solid_sigma.real,
                    "solid_sigma_imag_s_m": solid_sigma.imag,
                    "effective_sigma_real_s_m": result.effective_conductivity_s_m.real,
                    "effective_sigma_imag_s_m": result.effective_conductivity_s_m.imag,
                    "mean_current_real_a_m2": result.mean_current_density_a_m2.real,
                    "mean_current_imag_a_m2": result.mean_current_density_a_m2.imag,
                    "relative_residual_norm": result.residual_norm,
                    "solver": result.solver,
                }
            )
            print(
                f"{used_frequency:g} Hz {direction}: "
                f"sigma_eff={result.effective_conductivity_s_m.real:.6e}"
                f"+{result.effective_conductivity_s_m.imag:.6e}j S/m, "
                f"residual={result.residual_norm:.3e}"
            )

    output_csv = out_dir / "berea_subvolume_ac3d_sweep.csv"
    pd.DataFrame(rows).to_csv(output_csv, index=False)
    metadata = {
        "raw": str(Path(args.raw)),
        "shape": shape,
        "crop_start": start,
        "crop_size": size,
        "pore_label": args.pore_label,
        "solid_label": args.solid_label,
        "voxel_size_m": args.voxel_size_m,
        "spectra": str(Path(args.spectra)),
        "frequencies_requested_hz": args.frequencies,
        "directions": args.directions,
        "label_counts": label_count_map,
        "pore_fraction": label_count_map.get(args.pore_label, 0) / int(np.prod(size)),
        "water_sigma_source": "apparent_water_sigma_* columns from spectra",
        "solid_sigma_formula": "1j * omega * epsilon_s",
        "parameters": params.__dict__,
    }
    metadata_path = out_dir / "berea_subvolume_ac3d_sweep.metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", output_csv)
    print("wrote", metadata_path)


if __name__ == "__main__":
    main()
