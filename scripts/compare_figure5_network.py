#!/usr/bin/env python3
"""Compare pnextract pore/throat distributions against Figure5.xlsx."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
}


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
                text = "".join(t.text or "" for t in si.iter(f"{{{NS['a']}}}t"))
                shared.append(html.unescape(text))

        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        out: list[list[str]] = []
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
            out.append([values.get(i, "") for i in range(max_col + 1)])
        return out


def load_figure5(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = read_xlsx_sheet1(path)
    data = rows[1:]
    pore_rows = []
    throat_rows = []
    for row in data:
        if len(row) >= 2 and row[0] and row[1]:
            pore_rows.append({"size_m": float(row[0]), "relative_volume": float(row[1])})
        if len(row) >= 4 and row[2] and row[3]:
            throat_rows.append({"size_m": float(row[2]), "relative_volume": float(row[3])})
    return pd.DataFrame(pore_rows), pd.DataFrame(throat_rows)


def log_edges(centers: np.ndarray) -> np.ndarray:
    centers = np.asarray(centers, dtype=float)
    mids = np.sqrt(centers[:-1] * centers[1:])
    first = centers[0] ** 2 / mids[0]
    last = centers[-1] ** 2 / mids[-1]
    return np.concatenate([[first], mids, [last]])


def weighted_distribution(values: np.ndarray, weights: np.ndarray, centers: np.ndarray) -> np.ndarray:
    edges = log_edges(centers)
    hist, _ = np.histogram(values, bins=edges, weights=weights)
    total = hist.sum()
    return hist / total if total else hist


def metrics(reference: np.ndarray, candidate: np.ndarray, centers: np.ndarray) -> dict[str, float]:
    ref = reference / reference.sum()
    cand = candidate / candidate.sum() if candidate.sum() else candidate
    return {
        "l1_distance": float(np.abs(ref - cand).sum()),
        "weighted_mean_reference_m": float(np.sum(centers * ref)),
        "weighted_mean_pnextract_m": float(np.sum(centers * cand)),
        "peak_reference_m": float(centers[int(ref.argmax())]),
        "peak_pnextract_m": float(centers[int(cand.argmax())]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network-dir", required=True)
    parser.add_argument("--figure5", default="论文数据/Figure5.xlsx")
    parser.add_argument("--outdir", default="outputs/figure5_pnextract_comparison")
    parser.add_argument("--figure-out", default="figures/figure5_pnextract_comparison.png")
    args = parser.parse_args()

    network_dir = Path(args.network_dir)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    figure_out = Path(args.figure_out)
    figure_out.parent.mkdir(parents=True, exist_ok=True)

    pores = pd.read_csv(network_dir / "pores.csv")
    throats = pd.read_csv(network_dir / "throats.csv")
    paper_pores, paper_throats = load_figure5(Path(args.figure5))

    paper_pore_y = paper_pores["relative_volume"].to_numpy(dtype=float)
    paper_pore_y = paper_pore_y / paper_pore_y.sum()
    paper_throat_y = paper_throats["relative_volume"].to_numpy(dtype=float)
    paper_throat_y = paper_throat_y / paper_throat_y.sum()

    pore_centers = paper_pores["size_m"].to_numpy(dtype=float)
    throat_centers = paper_throats["size_m"].to_numpy(dtype=float)

    pn_pore_y = weighted_distribution(
        pores["pore_radius_m"].to_numpy(dtype=float),
        pores["pore_volume_m3"].to_numpy(dtype=float),
        pore_centers,
    )
    pn_throat_y = weighted_distribution(
        throats["throat_length_m"].to_numpy(dtype=float),
        throats["throat_volume_m3"].to_numpy(dtype=float),
        throat_centers,
    )

    pore_compare = pd.DataFrame(
        {
            "kind": "pore_node_size",
            "size_m": pore_centers,
            "paper_relative_volume": paper_pore_y,
            "pnextract_relative_volume": pn_pore_y,
        }
    )
    throat_compare = pd.DataFrame(
        {
            "kind": "pore_throat_length",
            "size_m": throat_centers,
            "paper_relative_volume": paper_throat_y,
            "pnextract_relative_volume": pn_throat_y,
        }
    )
    comparison = pd.concat([pore_compare, throat_compare], ignore_index=True)
    comparison.to_csv(outdir / "figure5_pnextract_comparison.csv", index=False)

    summary = {
        "pore_node_size": metrics(paper_pore_y, pn_pore_y, pore_centers),
        "pore_throat_length": metrics(paper_throat_y, pn_throat_y, throat_centers),
        "notes": [
            "pnextract pore node size is compared using node2 pore_radius_m weighted by pore_volume_m3.",
            "pnextract pore throat length is compared using link2 throat_length_m weighted by throat_volume_m3.",
            "Figure5 paper relative volumes were normalized to sum to one before comparison.",
        ],
    }
    (outdir / "figure5_pnextract_metrics.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    axes[0].plot(pore_centers * 1e6, paper_pore_y, "o-", label="Paper Figure 5")
    axes[0].plot(pore_centers * 1e6, pn_pore_y, "s--", label="pnextract")
    axes[0].set_xscale("log")
    axes[0].set_xlabel("Pore node size / radius (um)")
    axes[0].set_ylabel("Relative volume")
    axes[0].set_title("Pore node size distribution")
    axes[0].legend()

    axes[1].plot(throat_centers * 1e6, paper_throat_y, "o-", label="Paper Figure 5")
    axes[1].plot(throat_centers * 1e6, pn_throat_y, "s--", label="pnextract")
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Pore throat length (um)")
    axes[1].set_ylabel("Relative volume")
    axes[1].set_title("Pore throat length distribution")
    axes[1].legend()

    fig.savefig(figure_out, dpi=220)
    plt.close(fig)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("wrote", figure_out)


if __name__ == "__main__":
    main()

