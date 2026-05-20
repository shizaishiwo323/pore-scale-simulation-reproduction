"""Complex periodic finite-volume solver for AC3D-style conductivity problems.

The solver computes the periodic correction potential ``u`` for a prescribed
macroscopic electric field ``E``:

``div(sigma * (E - grad(u))) = 0``.

This is the cell-centered counterpart of the AC3D equation used by Niu et al.
(2020). Face conductivities use the half-cell series, or harmonic, average
listed in the reproduction plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla


Direction = Literal["x", "y", "z"] | int


@dataclass(frozen=True)
class AC3DResult:
    """Result for one imposed-field direction."""

    direction: str
    effective_conductivity_s_m: complex
    mean_current_density_a_m2: complex
    field_strength_v_m: float
    residual_norm: float
    potential: np.ndarray
    solver: str
    iterations: int | None = None


@dataclass(frozen=True)
class AC3DIterativeResult:
    """Result from the matrix-free Krylov solver."""

    direction: str
    effective_conductivity_s_m: complex
    mean_current_density_a_m2: complex
    field_strength_v_m: float
    residual_norm: float
    potential: np.ndarray | None
    solver: str
    iterations: int
    info: int


def direction_to_axis(direction: Direction) -> int:
    if isinstance(direction, int):
        if direction not in (0, 1, 2):
            raise ValueError("integer direction must be 0, 1, or 2")
        return direction
    mapping = {"x": 0, "y": 1, "z": 2}
    try:
        return mapping[direction.lower()]
    except KeyError as exc:
        raise ValueError("direction must be one of x, y, z, 0, 1, or 2") from exc


def axis_to_direction(axis: int) -> str:
    return ("x", "y", "z")[axis]


def harmonic_face_conductivity(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Half-cell series average: ``1 / (0.5/sigma_i + 0.5/sigma_j)``."""

    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    denominator = left + right
    out = np.zeros(np.broadcast_shapes(left.shape, right.shape), dtype=np.complex128)
    mask = np.abs(denominator) > np.finfo(float).tiny
    out[mask] = 2.0 * left[mask] * right[mask] / denominator[mask]
    return out


def phase_conductivity_grid(
    labels: np.ndarray,
    pore_label: int,
    solid_label: int,
    water_conductivity_s_m: complex,
    solid_conductivity_s_m: complex,
) -> np.ndarray:
    """Map a two-phase label volume to complex conductivity."""

    labels = np.asarray(labels)
    sigma = np.empty(labels.shape, dtype=np.complex128)
    pore_mask = labels == pore_label
    solid_mask = labels == solid_label
    if not np.all(pore_mask | solid_mask):
        bad = np.unique(labels[~(pore_mask | solid_mask)])
        raise ValueError(f"unexpected labels in volume: {bad[:10]}")
    sigma[pore_mask] = water_conductivity_s_m
    sigma[solid_mask] = solid_conductivity_s_m
    return sigma


def build_periodic_system(
    conductivity_s_m: np.ndarray,
    direction: Direction,
    field_strength_v_m: float = 1.0,
    voxel_size_m: float = 1.0,
) -> tuple[sp.csr_matrix, np.ndarray]:
    """Build the sparse linear system for the periodic correction potential."""

    sigma = np.asarray(conductivity_s_m, dtype=np.complex128)
    if sigma.ndim != 3:
        raise ValueError("conductivity_s_m must be a 3-D array")
    if field_strength_v_m == 0:
        raise ValueError("field_strength_v_m must be non-zero")
    if voxel_size_m <= 0:
        raise ValueError("voxel_size_m must be positive")

    drive_axis = direction_to_axis(direction)
    n_cells = int(np.prod(sigma.shape))
    indices = np.arange(n_cells, dtype=np.int64).reshape(sigma.shape)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    data: list[np.ndarray] = []
    macro_divergence = np.zeros(n_cells, dtype=np.complex128)

    for axis in range(3):
        if sigma.shape[axis] <= 1:
            continue

        neighbor_indices = np.roll(indices, -1, axis=axis).ravel()
        cell_indices = indices.ravel()
        face_sigma = harmonic_face_conductivity(sigma, np.roll(sigma, -1, axis=axis)).ravel()

        rows.extend([cell_indices, cell_indices, neighbor_indices, neighbor_indices])
        cols.extend([cell_indices, neighbor_indices, neighbor_indices, cell_indices])
        data.extend([face_sigma, -face_sigma, face_sigma, -face_sigma])

        if axis == drive_axis:
            drive = face_sigma * field_strength_v_m * voxel_size_m
            np.add.at(macro_divergence, cell_indices, drive)
            np.add.at(macro_divergence, neighbor_indices, -drive)

    matrix = sp.coo_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))), shape=(n_cells, n_cells))
    rhs = -macro_divergence

    matrix = matrix.tolil()
    matrix[0, :] = 0.0
    matrix[0, 0] = 1.0
    rhs[0] = 0.0
    return matrix.tocsr(), rhs


def face_conductivity_forward(conductivity_s_m: np.ndarray, axis: int) -> np.ndarray:
    """Conductivity on positive-axis periodic faces."""

    return harmonic_face_conductivity(conductivity_s_m, np.roll(conductivity_s_m, -1, axis=axis))


def matrix_free_matvec(conductivity_s_m: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """Apply the periodic AC3D operator without building a sparse matrix."""

    sigma = np.asarray(conductivity_s_m, dtype=np.complex128)
    x = np.asarray(vector, dtype=np.complex128).reshape(sigma.shape)
    y = np.zeros_like(x)
    for axis in range(3):
        if sigma.shape[axis] <= 1:
            continue
        g_forward = face_conductivity_forward(sigma, axis)
        g_backward = np.roll(g_forward, 1, axis=axis)
        y += g_forward * (x - np.roll(x, -1, axis=axis))
        y += g_backward * (x - np.roll(x, 1, axis=axis))
    y = y.ravel()
    y[0] = vector[0]
    return y


def matrix_free_rhs(
    conductivity_s_m: np.ndarray,
    direction: Direction,
    field_strength_v_m: float = 1.0,
    voxel_size_m: float = 1.0,
) -> np.ndarray:
    """Right-hand side for the imposed macroscopic field."""

    sigma = np.asarray(conductivity_s_m, dtype=np.complex128)
    axis = direction_to_axis(direction)
    g_forward = face_conductivity_forward(sigma, axis)
    g_backward = np.roll(g_forward, 1, axis=axis)
    macro_divergence = field_strength_v_m * voxel_size_m * (g_forward - g_backward)
    rhs = -macro_divergence.ravel()
    rhs[0] = 0.0
    return rhs


def jacobi_inverse_diagonal(conductivity_s_m: np.ndarray) -> np.ndarray:
    """Jacobi preconditioner for the matrix-free periodic operator."""

    sigma = np.asarray(conductivity_s_m, dtype=np.complex128)
    diagonal = np.zeros(sigma.shape, dtype=np.complex128)
    for axis in range(3):
        if sigma.shape[axis] <= 1:
            continue
        g_forward = face_conductivity_forward(sigma, axis)
        diagonal += g_forward + np.roll(g_forward, 1, axis=axis)
    diagonal = diagonal.ravel()
    diagonal[0] = 1.0
    inverse = np.zeros_like(diagonal)
    mask = np.abs(diagonal) > np.finfo(float).tiny
    inverse[mask] = 1.0 / diagonal[mask]
    return inverse


def mean_current_density(
    conductivity_s_m: np.ndarray,
    potential: np.ndarray,
    direction: Direction,
    field_strength_v_m: float = 1.0,
    voxel_size_m: float = 1.0,
) -> complex:
    """Compute volume-averaged current density for one direction."""

    axis = direction_to_axis(direction)
    sigma = np.asarray(conductivity_s_m, dtype=np.complex128)
    u = np.asarray(potential, dtype=np.complex128).reshape(sigma.shape)
    face_sigma = face_conductivity_forward(sigma, axis)
    face_field = field_strength_v_m - (np.roll(u, -1, axis=axis) - u) / voxel_size_m
    return complex(np.mean(face_sigma * face_field))


def solve_ac3d(
    conductivity_s_m: np.ndarray,
    direction: Direction = "x",
    field_strength_v_m: float = 1.0,
    voxel_size_m: float = 1.0,
    solver: Literal["direct"] = "direct",
) -> AC3DResult:
    """Solve one complex effective-conductivity problem."""

    if solver != "direct":
        raise ValueError("only the direct sparse solver is implemented in this validated prototype")

    sigma = np.asarray(conductivity_s_m, dtype=np.complex128)
    axis = direction_to_axis(direction)
    matrix, rhs = build_periodic_system(sigma, axis, field_strength_v_m, voxel_size_m)
    potential_flat = spla.spsolve(matrix, rhs)
    residual = matrix @ potential_flat - rhs
    residual_norm = float(np.linalg.norm(residual) / max(np.linalg.norm(rhs), np.finfo(float).eps))
    potential = potential_flat.reshape(sigma.shape)

    mean_current = mean_current_density(sigma, potential, axis, field_strength_v_m, voxel_size_m)
    effective = mean_current / field_strength_v_m

    return AC3DResult(
        direction=axis_to_direction(axis),
        effective_conductivity_s_m=complex(effective),
        mean_current_density_a_m2=mean_current,
        field_strength_v_m=field_strength_v_m,
        residual_norm=residual_norm,
        potential=potential,
        solver=solver,
    )


def solve_ac3d_matrix_free(
    conductivity_s_m: np.ndarray,
    direction: Direction = "x",
    field_strength_v_m: float = 1.0,
    voxel_size_m: float = 1.0,
    rtol: float = 1.0e-8,
    atol: float = 0.0,
    maxiter: int | None = None,
    use_jacobi: bool = True,
    return_potential: bool = True,
) -> AC3DIterativeResult:
    """Solve with a matrix-free BiCGSTAB Krylov iteration.

    This prototype keeps the same operator as ``solve_ac3d`` but avoids
    materializing the sparse matrix. It still stores several Krylov vectors in
    memory, so it is intended for medium grids unless paired with a lower-level
    streaming implementation.
    """

    sigma = np.asarray(conductivity_s_m, dtype=np.complex128)
    axis = direction_to_axis(direction)
    n_cells = int(np.prod(sigma.shape))
    rhs = matrix_free_rhs(sigma, axis, field_strength_v_m, voxel_size_m)

    operator = spla.LinearOperator(
        (n_cells, n_cells),
        matvec=lambda vector: matrix_free_matvec(sigma, vector),
        dtype=np.complex128,
    )
    preconditioner = None
    if use_jacobi:
        inverse_diagonal = jacobi_inverse_diagonal(sigma)
        preconditioner = spla.LinearOperator(
            (n_cells, n_cells),
            matvec=lambda vector: inverse_diagonal * vector,
            dtype=np.complex128,
        )

    iterations = 0

    def callback(_xk: np.ndarray) -> None:
        nonlocal iterations
        iterations += 1

    solution, info = spla.bicgstab(operator, rhs, rtol=rtol, atol=atol, maxiter=maxiter, M=preconditioner, callback=callback)
    residual = matrix_free_matvec(sigma, solution) - rhs
    residual_norm = float(np.linalg.norm(residual) / max(np.linalg.norm(rhs), np.finfo(float).eps))
    potential = solution.reshape(sigma.shape)
    mean_current = mean_current_density(sigma, potential, axis, field_strength_v_m, voxel_size_m)
    effective = mean_current / field_strength_v_m

    return AC3DIterativeResult(
        direction=axis_to_direction(axis),
        effective_conductivity_s_m=complex(effective),
        mean_current_density_a_m2=mean_current,
        field_strength_v_m=field_strength_v_m,
        residual_norm=residual_norm,
        potential=potential if return_potential else None,
        solver="matrix_free_bicgstab_jacobi" if use_jacobi else "matrix_free_bicgstab",
        iterations=iterations,
        info=int(info),
    )


def effective_conductivity_tensor_diagonal(
    conductivity_s_m: np.ndarray,
    field_strength_v_m: float = 1.0,
    voxel_size_m: float = 1.0,
) -> dict[str, AC3DResult]:
    """Solve x, y, and z imposed-field directions independently."""

    return {
        direction: solve_ac3d(conductivity_s_m, direction, field_strength_v_m, voxel_size_m)
        for direction in ("x", "y", "z")
    }
