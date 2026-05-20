"""Electrochemical polarization models from Niu et al. (2020).

The internal complex convention follows the AC3D-style engineering form
``sigma* = sigma_real + 1j * sigma_imag`` used later in the finite-difference
solver. This is also the algebraic convention used by Equations 14 and 17-21
when written with ``i omega`` terms.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


EPSILON_0 = 8.85e-12


@dataclass(frozen=True)
class PolarizationParameters:
    """Parameters used in the Berea simulations of Niu et al. (2020)."""

    surface_conductance_s: float = 1.3e-9
    diffusion_coefficient_m2_s: float = 1.3e-9
    dynamic_pore_size_m: float = 2.7e-6
    membrane_polarizability: float = 0.01
    water_conductivity_s_m: float = 0.043
    epsilon_0_f_m: float = EPSILON_0
    water_relative_permittivity: float = 80.0
    solid_relative_permittivity: float = 7.0

    @property
    def water_permittivity_f_m(self) -> float:
        return self.water_relative_permittivity * self.epsilon_0_f_m

    @property
    def solid_permittivity_f_m(self) -> float:
        return self.solid_relative_permittivity * self.epsilon_0_f_m


def angular_frequency(frequency_hz: np.ndarray | float) -> np.ndarray:
    return 2.0 * np.pi * np.atleast_1d(np.asarray(frequency_hz, dtype=float))


def normalize_weights(weights: np.ndarray) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    total = weights.sum()
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    return weights / total


def pore_relaxation_time(radius_m: np.ndarray, diffusion_coefficient_m2_s: float) -> np.ndarray:
    radius_m = np.asarray(radius_m, dtype=float)
    return radius_m**2 / (2.0 * diffusion_coefficient_m2_s)


def membrane_relaxation_time(length_m: np.ndarray, diffusion_coefficient_m2_s: float) -> np.ndarray:
    length_m = np.asarray(length_m, dtype=float)
    return length_m**2 / (4.0 * diffusion_coefficient_m2_s)


def elementary_pore_conductance(
    frequency_hz: np.ndarray | float,
    radius_m: np.ndarray,
    params: PolarizationParameters = PolarizationParameters(),
) -> np.ndarray:
    """Equation 17 for each pore radius.

    Returns an array with shape ``(n_frequency, n_radius)``.
    """

    omega = angular_frequency(frequency_hz)[:, None]
    tau = pore_relaxation_time(radius_m, params.diffusion_coefficient_m2_s)[None, :]
    iwt = 1j * omega * tau
    return params.surface_conductance_s * iwt / (1.0 + iwt)


def pore_polarization_conductance(
    frequency_hz: np.ndarray | float,
    radius_m: np.ndarray,
    weights: np.ndarray,
    params: PolarizationParameters = PolarizationParameters(),
) -> np.ndarray:
    """Equations 9 and 17 as a weighted sum over the pore-size distribution."""

    weights = normalize_weights(weights)
    elementary = elementary_pore_conductance(frequency_hz, radius_m, params)
    return elementary @ weights


def elementary_membrane_impedance(
    frequency_hz: np.ndarray | float,
    length_m: np.ndarray,
    zdc_ohm: np.ndarray,
    params: PolarizationParameters = PolarizationParameters(),
) -> np.ndarray:
    """Equation 19 for each pore-throat length and dc resistance."""

    omega = angular_frequency(frequency_hz)[:, None]
    tau = membrane_relaxation_time(length_m, params.diffusion_coefficient_m2_s)[None, :]
    zdc = np.asarray(zdc_ohm, dtype=float)[None, :]
    root = np.sqrt(1j * omega * tau)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        frac = (1.0 - np.exp(-2.0 * root)) / (2.0 * root)
    small = np.abs(root) < 1.0e-6
    if np.any(small):
        s = root[small]
        frac[small] = 1.0 - s + (2.0 / 3.0) * s**2 - (1.0 / 3.0) * s**3
    frac = np.where(np.isfinite(frac), frac, 1.0)
    bracket = 1.0 - params.membrane_polarizability * (1.0 - frac)
    return zdc * bracket


def elementary_membrane_conductance_perturbation(
    frequency_hz: np.ndarray | float,
    length_m: np.ndarray,
    zdc_ohm: np.ndarray,
    params: PolarizationParameters = PolarizationParameters(),
) -> np.ndarray:
    """Equations 19 and 21 for each pore throat."""

    zdc = np.asarray(zdc_ohm, dtype=float)[None, :]
    z_star = elementary_membrane_impedance(frequency_hz, length_m, zdc_ohm, params)
    return 1.0 / z_star - 1.0 / zdc


def membrane_polarization_conductance(
    frequency_hz: np.ndarray | float,
    length_m: np.ndarray,
    weights: np.ndarray,
    zdc_ohm: np.ndarray,
    params: PolarizationParameters = PolarizationParameters(),
) -> np.ndarray:
    """Equations 10, 19, and 21 as a weighted sum over pore throats."""

    weights = normalize_weights(weights)
    elementary = elementary_membrane_conductance_perturbation(frequency_hz, length_m, zdc_ohm, params)
    return elementary @ weights


def upscale_conductance_to_water_conductivity(
    conductance_s: np.ndarray,
    params: PolarizationParameters = PolarizationParameters(),
) -> np.ndarray:
    """Equation 12: convert conductance in S to volumetric conductivity in S/m."""

    return 2.0 * np.asarray(conductance_s) / params.dynamic_pore_size_m


def throat_cross_section_area_from_radius_shape_factor(radius_m: np.ndarray, shape_factor: np.ndarray) -> np.ndarray:
    """Invert pnextract's shape-factor definition G = R^2 / (4 A)."""

    radius_m = np.asarray(radius_m, dtype=float)
    shape_factor = np.asarray(shape_factor, dtype=float)
    if np.any(shape_factor <= 0):
        raise ValueError("shape factors must be positive")
    return radius_m**2 / (4.0 * shape_factor)


def throat_zdc_from_geometry(
    length_m: np.ndarray,
    radius_m: np.ndarray,
    shape_factor: np.ndarray,
    water_conductivity_s_m: float,
) -> np.ndarray:
    """Approximate dc throat resistance from pnextract throat geometry."""

    length_m = np.asarray(length_m, dtype=float)
    area_m2 = throat_cross_section_area_from_radius_shape_factor(radius_m, shape_factor)
    conductance = water_conductivity_s_m * area_m2 / np.maximum(length_m, np.finfo(float).tiny)
    return 1.0 / np.maximum(conductance, np.finfo(float).tiny)


def apparent_water_conductivity(
    frequency_hz: np.ndarray | float,
    delta_sigma_w_s_m: np.ndarray,
    params: PolarizationParameters = PolarizationParameters(),
) -> np.ndarray:
    """Equation 14 water-phase conductivity including polarization increment."""

    omega = angular_frequency(frequency_hz)
    return params.water_conductivity_s_m + 1j * omega * params.water_permittivity_f_m + delta_sigma_w_s_m
