import numpy as np

from pore_scale_electrical.polarization import (
    PolarizationParameters,
    membrane_polarization_conductance,
    pore_polarization_conductance,
    throat_cross_section_area_from_radius_shape_factor,
    upscale_conductance_to_water_conductivity,
)


def test_pore_polarization_low_and_high_frequency_limits():
    params = PolarizationParameters(surface_conductance_s=2.0e-9, diffusion_coefficient_m2_s=1.0e-9)
    radii = np.array([1.0e-6, 10.0e-6])
    weights = np.array([0.25, 0.75])
    values = pore_polarization_conductance(np.array([1.0e-12, 1.0e12]), radii, weights, params)

    assert abs(values[0]) < 1e-18
    assert np.isclose(values[-1].real, params.surface_conductance_s, rtol=1e-5)
    assert abs(values[-1].imag) < 1e-13


def test_membrane_polarization_low_and_high_frequency_limits():
    params = PolarizationParameters(membrane_polarizability=0.01, diffusion_coefficient_m2_s=1.0e-9)
    lengths = np.array([5.0e-6, 20.0e-6])
    zdc = np.array([100.0, 200.0])
    weights = np.array([0.5, 0.5])
    values = membrane_polarization_conductance(np.array([1.0e-20, 1.0e12]), lengths, weights, zdc, params)

    high_limit = np.average((params.membrane_polarizability / (1.0 - params.membrane_polarizability)) / zdc, weights=weights)
    assert abs(values[0]) < 1e-12
    assert np.isclose(values[-1].real, high_limit, rtol=1e-5)
    assert abs(values[-1].imag) < 1e-8


def test_upscale_conductance_to_water_conductivity():
    params = PolarizationParameters(dynamic_pore_size_m=2.0e-6)
    assert upscale_conductance_to_water_conductivity(np.array([3.0e-9]), params)[0] == 3.0e-3


def test_pnextract_shape_factor_area_inversion():
    radius = np.array([2.0])
    shape_factor = np.array([0.25])
    area = throat_cross_section_area_from_radius_shape_factor(radius, shape_factor)
    assert np.allclose(area, np.array([4.0]))
