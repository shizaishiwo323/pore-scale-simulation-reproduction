import numpy as np

from pore_scale_electrical.ac3d_solver import (
    harmonic_face_conductivity,
    matrix_free_matvec,
    phase_conductivity_grid,
    solve_ac3d,
    solve_ac3d_matrix_free,
)


def test_harmonic_face_conductivity_matches_half_cell_series():
    left = np.array([1.0 + 0.5j])
    right = np.array([3.0 + 0.25j])
    expected = 1.0 / (0.5 / left + 0.5 / right)

    assert np.allclose(harmonic_face_conductivity(left, right), expected)


def test_uniform_complex_medium_returns_input_conductivity():
    sigma0 = 0.043 + 2.0e-4j
    grid = np.full((4, 3, 5), sigma0, dtype=np.complex128)

    for direction in ("x", "y", "z"):
        result = solve_ac3d(grid, direction=direction)
        assert np.isclose(result.effective_conductivity_s_m, sigma0, rtol=1e-11, atol=1e-13)
        assert result.residual_norm < 1e-10


def test_parallel_layers_match_arithmetic_mean():
    sigma1 = 1.0 + 0.1j
    sigma2 = 4.0 + 0.2j
    grid = np.empty((4, 4, 3), dtype=np.complex128)
    grid[:, :2, :] = sigma1
    grid[:, 2:, :] = sigma2

    result = solve_ac3d(grid, direction="x")
    expected = 0.5 * (sigma1 + sigma2)

    assert np.isclose(result.effective_conductivity_s_m, expected, rtol=1e-10, atol=1e-12)


def test_series_layers_match_harmonic_mean():
    sigma1 = 1.0 + 0.1j
    sigma2 = 4.0 + 0.2j
    grid = np.empty((4, 3, 3), dtype=np.complex128)
    grid[:2, :, :] = sigma1
    grid[2:, :, :] = sigma2

    result = solve_ac3d(grid, direction="x")
    expected = 1.0 / (0.5 / sigma1 + 0.5 / sigma2)

    assert np.isclose(result.effective_conductivity_s_m, expected, rtol=1e-10, atol=1e-12)


def test_matrix_free_operator_matches_explicit_matrix():
    rng = np.random.default_rng(42)
    sigma = 0.1 + rng.random((3, 4, 2)) + 1j * rng.random((3, 4, 2)) * 0.01
    vector = rng.random(sigma.size) + 1j * rng.random(sigma.size)

    from pore_scale_electrical.ac3d_solver import build_periodic_system

    matrix, _rhs = build_periodic_system(sigma, direction="x")
    assert np.allclose(matrix @ vector, matrix_free_matvec(sigma, vector))


def test_matrix_free_solver_matches_direct_solver():
    grid = np.empty((4, 4, 3), dtype=np.complex128)
    grid[:, :2, :] = 1.0 + 0.1j
    grid[:, 2:, :] = 4.0 + 0.2j

    direct = solve_ac3d(grid, direction="x")
    iterative = solve_ac3d_matrix_free(grid, direction="x", rtol=1e-10, maxiter=200)

    assert iterative.info == 0
    assert iterative.residual_norm < 1e-8
    assert np.isclose(iterative.effective_conductivity_s_m, direct.effective_conductivity_s_m, rtol=1e-8, atol=1e-10)


def test_phase_label_mapping_rejects_unknown_labels():
    labels = np.array([[[1, 2], [1, 3]]], dtype=np.uint16)

    try:
        phase_conductivity_grid(labels, pore_label=1, solid_label=2, water_conductivity_s_m=1.0, solid_conductivity_s_m=0.0)
    except ValueError as exc:
        assert "unexpected labels" in str(exc)
    else:
        raise AssertionError("unknown labels should raise ValueError")
