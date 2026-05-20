#!/usr/bin/env python3
"""Run one matrix-free AC3D solve with a resource preflight."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pore_scale_electrical.ac3d_solver import phase_conductivity_grid, solve_ac3d_matrix_free  # noqa: E402
from pore_scale_electrical.polarization import PolarizationParameters  # noqa: E402


def parse_int3(values: list[str], name: str) -> tuple[int, int, int]:
    if len(values) != 3:
        raise ValueError(f"{name} expects exactly three integers")
    parsed = tuple(int(v) for v in values)
    if any(v < 0 for v in parsed):
        raise ValueError(f"{name} must be non-negative")
    return parsed


def available_memory_bytes() -> int | None:
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_AVPHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int(pages * page_size)
        except (ValueError, OSError):
            return None
    return None


def total_memory_bytes() -> int | None:
    if sys.platform == "darwin":
        import subprocess

        try:
            return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
        except Exception:
            return None
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int(pages * page_size)
        except (ValueError, OSError):
            return None
    return None


def estimate_python_matrix_free_peak_bytes(n_cells: int) -> int:
    """Conservative peak for the current NumPy/SciPy matrix-free prototype."""

    complex_vector = 16 * n_cells
    labels = 2 * n_cells
    # sigma + rhs + inverse diagonal + Krylov work vectors + NumPy roll temporaries.
    return labels + 20 * complex_vector


def read_volume(raw_path: Path, shape: tuple[int, int, int], crop_start: tuple[int, int, int] | None, crop_size: tuple[int, int, int] | None) -> np.ndarray:
    volume = np.memmap(raw_path, dtype="<u2", mode="r", shape=shape, order="C")
    if crop_start is None or crop_size is None:
        return np.asarray(volume)
    stop = tuple(s + n for s, n in zip(crop_start, crop_size))
    if any(e > full for e, full in zip(stop, shape)):
        raise ValueError(f"requested subvolume {crop_start}:{stop} exceeds shape {shape}")
    selection = tuple(slice(s, e) for s, e in zip(crop_start, stop))
    return np.asarray(volume[selection])


def nearest_spectrum_row(path: Path, frequency_hz: float) -> pd.Series:
    spectra = pd.read_csv(path)
    idx = np.abs(np.log(spectra["frequency_hz"].to_numpy(dtype=float)) - np.log(frequency_hz)).argmin()
    return spectra.iloc[int(idx)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=str(ROOT / "论文数据" / "microCT_Berea.raw"))
    parser.add_argument("--shape", nargs=3, default=("350", "350", "350"))
    parser.add_argument("--crop-start", nargs=3)
    parser.add_argument("--crop-size", nargs=3)
    parser.add_argument("--pore-label", type=int, default=1)
    parser.add_argument("--solid-label", type=int, default=2)
    parser.add_argument("--voxel-size-m", type=float, default=2.8e-6)
    parser.add_argument("--spectra", default=str(ROOT / "outputs" / "polarization_spectra_from_pnextract.csv"))
    parser.add_argument("--frequency", type=float, default=1.0)
    parser.add_argument("--direction", choices=["x", "y", "z"], default="x")
    parser.add_argument("--rtol", type=float, default=1.0e-8)
    parser.add_argument("--maxiter", type=int, default=1000)
    parser.add_argument("--out-dir", default=str(ROOT / "outputs" / "ac3d_matrix_free_single"))
    parser.add_argument("--force", action="store_true", help="run even if memory preflight fails")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    shape = parse_int3(args.shape, "--shape")
    crop_start = parse_int3(args.crop_start, "--crop-start") if args.crop_start else None
    crop_size = parse_int3(args.crop_size, "--crop-size") if args.crop_size else None
    solve_shape = crop_size if crop_size else shape
    n_cells = int(np.prod(solve_shape))
    estimated_peak = estimate_python_matrix_free_peak_bytes(n_cells)
    total_mem = total_memory_bytes()
    available_mem = available_memory_bytes()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = out_dir / "matrix_free_single_preflight.json"
    preflight = {
        "shape": shape,
        "crop_start": crop_start,
        "solve_shape": solve_shape,
        "n_cells": n_cells,
        "estimated_python_peak_bytes": estimated_peak,
        "estimated_python_peak_gib": estimated_peak / 1024**3,
        "total_memory_bytes": total_mem,
        "total_memory_gib": None if total_mem is None else total_mem / 1024**3,
        "available_memory_bytes": available_mem,
        "available_memory_gib": None if available_mem is None else available_mem / 1024**3,
        "memory_preflight_passed": total_mem is not None and estimated_peak < 0.65 * total_mem,
        "solver": "matrix_free_bicgstab_jacobi_python_numpy",
        "frequency_requested_hz": args.frequency,
        "direction": args.direction,
    }
    metadata_path.write_text(json.dumps(preflight, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(preflight, indent=2, ensure_ascii=False))

    if args.preflight_only:
        return
    if not preflight["memory_preflight_passed"] and not args.force:
        raise SystemExit(
            "Memory preflight failed for this Python/SciPy matrix-free prototype. "
            "Use a smaller crop, a native streaming solver, a larger-memory machine, or --force."
        )

    params = PolarizationParameters()
    spectrum_row = nearest_spectrum_row(Path(args.spectra), args.frequency)
    used_frequency = float(spectrum_row["frequency_hz"])
    omega = 2.0 * np.pi * used_frequency
    water_sigma = complex(
        float(spectrum_row["apparent_water_sigma_real_s_m"]),
        float(spectrum_row["apparent_water_sigma_imag_s_m"]),
    )
    solid_sigma = 1j * omega * params.solid_permittivity_f_m

    labels = read_volume(Path(args.raw), shape, crop_start, crop_size)
    sigma_grid = phase_conductivity_grid(labels, args.pore_label, args.solid_label, water_sigma, solid_sigma)
    result = solve_ac3d_matrix_free(
        sigma_grid,
        direction=args.direction,
        voxel_size_m=args.voxel_size_m,
        rtol=args.rtol,
        maxiter=args.maxiter,
        use_jacobi=True,
        return_potential=False,
    )

    output = {
        **preflight,
        "frequency_hz": used_frequency,
        "water_sigma_real_s_m": water_sigma.real,
        "water_sigma_imag_s_m": water_sigma.imag,
        "solid_sigma_real_s_m": solid_sigma.real,
        "solid_sigma_imag_s_m": solid_sigma.imag,
        "effective_sigma_real_s_m": result.effective_conductivity_s_m.real,
        "effective_sigma_imag_s_m": result.effective_conductivity_s_m.imag,
        "mean_current_real_a_m2": result.mean_current_density_a_m2.real,
        "mean_current_imag_a_m2": result.mean_current_density_a_m2.imag,
        "relative_residual_norm": result.residual_norm,
        "iterations": result.iterations,
        "info": result.info,
    }
    result_path = out_dir / "matrix_free_single_result.json"
    result_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print("wrote", result_path)


if __name__ == "__main__":
    main()

