#!/usr/bin/env python3
"""Compute pore and membrane polarization spectra for Berea inputs."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pore_scale_electrical.polarization import (  # noqa: E402
    PolarizationParameters,
    apparent_water_conductivity,
    membrane_polarization_conductance,
    pore_polarization_conductance,
    throat_zdc_from_geometry,
    upscale_conductance_to_water_conductivity,
)


NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def col_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    idx = 0
    for ch in letters:
        idx = idx * 26 + ord(ch) - ord("A") + 1
    return idx - 1


def read_xlsx_sheet1(path: Path) -> list[list[str]]:
    with ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", NS):
                shared.append(html.unescape("".join(t.text or "" for t in si.iter(f"{{{NS['a']}}}t"))))
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in root.findall(".//a:sheetData/a:row", NS):
            values: dict[int, str] = {}
            max_col = -1
            for cell in row.findall("a:c", NS):
                idx = col_index(cell.attrib["r"])
                max_col = max(max_col, idx)
                value_node = cell.find("a:v", NS)
                value = "" if value_node is None else value_node.text or ""
                if cell.attrib.get("t") == "s" and value:
                    value = shared[int(value)]
                values[idx] = value
            rows.append([values.get(i, "") for i in range(max_col + 1)])
    return rows


def load_figure5(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = read_xlsx_sheet1(path)
    pore_rows = []
    throat_rows = []
    for row in rows[1:]:
        if len(row) >= 2 and row[0] and row[1]:
            pore_rows.append({"radius_m": float(row[0]), "weight": float(row[1])})
        if len(row) >= 4 and row[2] and row[3]:
            throat_rows.append({"length_m": float(row[2]), "weight": float(row[3])})
    return pd.DataFrame(pore_rows), pd.DataFrame(throat_rows)


def load_pnextract(network_dir: Path, params: PolarizationParameters) -> tuple[pd.DataFrame, pd.DataFrame]:
    pores = pd.read_csv(network_dir / "pores.csv")
    throats = pd.read_csv(network_dir / "throats.csv")
    pore_df = pd.DataFrame({"radius_m": pores["pore_radius_m"], "weight": pores["pore_volume_m3"]})
    zdc = throat_zdc_from_geometry(
        length_m=throats["throat_length_m"].to_numpy(dtype=float),
        radius_m=throats["throat_radius_m"].to_numpy(dtype=float),
        shape_factor=throats["throat_shape_factor"].to_numpy(dtype=float),
        water_conductivity_s_m=params.water_conductivity_s_m,
    )
    throat_df = pd.DataFrame(
        {
            "length_m": throats["throat_length_m"],
            "weight": throats["throat_volume_m3"],
            "zdc_ohm": zdc,
        }
    )
    return pore_df, throat_df


def default_frequencies() -> np.ndarray:
    return np.logspace(-3, 9, 97)


def compute_spectra(
    frequency_hz: np.ndarray,
    pores: pd.DataFrame,
    throats: pd.DataFrame,
    params: PolarizationParameters,
    figure5_zdc_ohm: float | None,
) -> tuple[pd.DataFrame, dict]:
    cp = pore_polarization_conductance(
        frequency_hz,
        pores["radius_m"].to_numpy(dtype=float),
        pores["weight"].to_numpy(dtype=float),
        params,
    )

    membrane_mode = "geometry_zdc"
    if "zdc_ohm" in throats.columns:
        zdc = throats["zdc_ohm"].to_numpy(dtype=float)
    elif figure5_zdc_ohm is not None:
        zdc = np.full(len(throats), figure5_zdc_ohm, dtype=float)
        membrane_mode = f"assumed_constant_zdc_{figure5_zdc_ohm:g}_ohm"
    else:
        zdc = None
        membrane_mode = "not_computed_missing_zdc"

    if zdc is None:
        cm = np.full_like(cp, np.nan + 1j * np.nan)
        c_total = cp
    else:
        cm = membrane_polarization_conductance(
            frequency_hz,
            throats["length_m"].to_numpy(dtype=float),
            throats["weight"].to_numpy(dtype=float),
            zdc,
            params,
        )
        c_total = cp + cm

    delta_pore = upscale_conductance_to_water_conductivity(cp, params)
    delta_membrane = upscale_conductance_to_water_conductivity(cm, params)
    delta_total = upscale_conductance_to_water_conductivity(c_total, params)
    sigma_w_app = apparent_water_conductivity(frequency_hz, delta_total, params)

    out = pd.DataFrame(
        {
            "frequency_hz": frequency_hz,
            "omega_rad_s": 2.0 * np.pi * frequency_hz,
            "pore_conductance_real_s": cp.real,
            "pore_conductance_imag_s": cp.imag,
            "membrane_conductance_real_s": cm.real,
            "membrane_conductance_imag_s": cm.imag,
            "total_conductance_real_s": c_total.real,
            "total_conductance_imag_s": c_total.imag,
            "delta_sigma_pore_real_s_m": delta_pore.real,
            "delta_sigma_pore_imag_s_m": delta_pore.imag,
            "delta_sigma_membrane_real_s_m": delta_membrane.real,
            "delta_sigma_membrane_imag_s_m": delta_membrane.imag,
            "delta_sigma_total_real_s_m": delta_total.real,
            "delta_sigma_total_imag_s_m": delta_total.imag,
            "apparent_water_sigma_real_s_m": sigma_w_app.real,
            "apparent_water_sigma_imag_s_m": sigma_w_app.imag,
        }
    )
    metadata = {
        "n_pores_or_bins": int(len(pores)),
        "n_throats_or_bins": int(len(throats)),
        "membrane_mode": membrane_mode,
        "parameters": params.__dict__,
    }
    return out, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["figure5", "pnextract"], required=True)
    parser.add_argument("--figure5", default=str(ROOT / "论文数据" / "Figure5.xlsx"))
    parser.add_argument("--network-dir", default=str(ROOT / "outputs" / "figure5_pnextract_comparison" / "network_parsed"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--metadata-out")
    parser.add_argument("--figure5-zdc-ohm", type=float, default=None)
    args = parser.parse_args()

    params = PolarizationParameters()
    if args.source == "figure5":
        pores, throats = load_figure5(Path(args.figure5))
    else:
        pores, throats = load_pnextract(Path(args.network_dir), params)

    spectra, metadata = compute_spectra(default_frequencies(), pores, throats, params, args.figure5_zdc_ohm)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    spectra.to_csv(out, index=False)

    metadata_out = Path(args.metadata_out) if args.metadata_out else out.with_suffix(".metadata.json")
    metadata_out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()

