# 阶段 5：AC3D 复数有限差分求解器验证记录

日期：2026-05-20

## 实现范围

本阶段实现了一个 AC3D-style 的三维周期边界复数有限体积/有限差分原型，用于求解论文 Equation 15：

```text
div(sigma* (E - grad(u))) = 0
```

其中 `u` 是周期扰动电势，`E` 是外加平均电场。相邻体素 face conductivity 使用半格串联调和平均：

```text
sigma_face = 1 / (0.5 / sigma_i + 0.5 / sigma_j)
```

有效复电导率用正向 face 平均电流密度计算：

```text
sigma_eff = <J_axis> / E_axis
```

代码入口：

- `src/pore_scale_electrical/ac3d_solver.py`
- `tests/test_ac3d_solver.py`
- `scripts/run_ac3d_frequency_sweep.py`

## 解析验证

测试命令：

```bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sip-simpeg
PYTHONPATH=src pytest -q tests/test_ac3d_solver.py tests/test_polarization.py
```

结果：

```text
9 passed in 0.29s
```

覆盖内容：

- 均匀复电导率介质：`sigma_eff = sigma_input`。
- 平行层状介质：外场平行层面时，结果等于算术平均。
- 串联层状介质：外场垂直层面时，结果等于调和平均。
- phase label 到水相/固相复电导率的映射检查。
- 阶段 4 极化模型回归测试。

## Berea 子体积验证

运行命令：

```bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sip-simpeg
python scripts/run_ac3d_frequency_sweep.py \
  --crop-start 224 80 288 \
  --crop-size 16 16 16 \
  --frequencies 0.001 1 1000 \
  --directions x y z \
  --out-dir outputs/ac3d_small_grid_validation
```

输入设置：

- 原始体数据：`论文数据/microCT_Berea.raw`
- 体数据形状：`350 x 350 x 350`
- 子体积起点：`(224, 80, 288)`
- 子体积大小：`16 x 16 x 16`
- 标签映射：`1 = pore/water`，`2 = solid`
- 子体积孔隙体素数：`946 / 4096`
- 子体积孔隙度：`0.23095703125`
- 水相复电导率来源：`outputs/polarization_spectra_from_pnextract.csv`
- 固相复电导率：`sigma_s* = i omega epsilon_s`

输出文件：

- `outputs/ac3d_small_grid_validation/berea_subvolume_ac3d_sweep.csv`
- `outputs/ac3d_small_grid_validation/berea_subvolume_ac3d_sweep.metadata.json`

关键结果：

| frequency Hz | direction | sigma_eff real S/m | sigma_eff imag S/m | residual |
| ---: | :---: | ---: | ---: | ---: |
| 0.001 | x | 2.781918e-17 | 7.036705e-13 | 1.108e-14 |
| 0.001 | y | 6.625518e-03 | 9.269130e-05 | 6.214e-15 |
| 0.001 | z | 5.912940e-03 | 8.272230e-05 | 8.743e-15 |
| 1 | x | 3.060272e-17 | 7.036699e-10 | 9.426e-15 |
| 1 | y | 8.948840e-03 | 1.191712e-03 | 4.968e-15 |
| 1 | z | 7.986388e-03 | 1.063543e-03 | 5.759e-15 |
| 1000 | x | 9.038348e-12 | 7.036695e-07 | 1.096e-14 |
| 1000 | y | 1.388710e-02 | 4.842454e-04 | 5.380e-15 |
| 1000 | z | 1.239353e-02 | 4.321866e-04 | 6.846e-15 |

解释：

- 该子体积孔隙度接近全体 Berea 的 label-1 体积分数。
- `y` 和 `z` 方向有明显水相导电贡献。
- `x` 方向实部接近零，说明这个 `16^3` 子体积在 x 方向未形成有效导电通路，主要剩固相介电响应；这对小体积验证是可接受的，但不能代表论文全体积各向同性结果。

## 全尺寸资源估计

当前实现使用显式稀疏矩阵和直接求解器，适合小网格验证，不适合直接跑完整 `350^3`。

粗略规模：

- `16^3`：4,096 unknowns，适合快速验证。
- `50^3`：125,000 unknowns，显式稀疏矩阵仍可尝试，直接解可能开始变慢。
- `100^3`：1,000,000 unknowns，建议改用迭代求解或矩阵自由算子。
- `350^3`：42,875,000 unknowns，约 `3N` 个周期 face、`~7N` 个稀疏非零项；仅 CSR 原始矩阵就达到数 GB 量级，直接求解的填充会远超普通工作站内存。

后续阶段建议：

- Figure 6-8 原型先用 `16^3`、`32^3`、`50^3` 子体积扫描。
- 全尺寸 Berea 应改造为矩阵自由 Krylov 求解器，并增加预条件器。
- 若要忠实贴近 NIST AC3D，还应继续从 `NISTIR 6269.pdf` 复原原始 `AC3D.F` 的迭代格式和收敛准则。

## 矩阵自由 Krylov 原型与完整 350^3 预检

日期：2026-05-20

已在 `src/pore_scale_electrical/ac3d_solver.py` 中加入矩阵自由算子、Jacobi 预条件和 BiCGSTAB 求解入口：

- `matrix_free_matvec`
- `matrix_free_rhs`
- `jacobi_inverse_diagonal`
- `solve_ac3d_matrix_free`

同时新增单次求解脚本：

- `scripts/run_ac3d_matrix_free_single.py`

验证命令：

```bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sip-simpeg
PYTHONPATH=src pytest -q tests/test_ac3d_solver.py tests/test_polarization.py
```

测试结果：

```text
11 passed in 0.29s
```

新增验证内容：

- 矩阵自由 `matvec` 与显式稀疏矩阵乘法逐项一致。
- 矩阵自由 BiCGSTAB + Jacobi 预条件与直接稀疏解在小网格上结果一致。

`16^3` 子体积矩阵自由求解命令：

```bash
python scripts/run_ac3d_matrix_free_single.py \
  --crop-start 224 80 288 \
  --crop-size 16 16 16 \
  --frequency 1 \
  --direction y \
  --rtol 1e-8 \
  --maxiter 500 \
  --out-dir outputs/ac3d_matrix_free_single_crop16
```

结果：

- `sigma_eff = 0.008948840312405408 + 0.0011917123490839255 i S/m`
- 相对残差：`9.83802857894948e-09`
- BiCGSTAB 迭代次数：`63`
- `info = 0`
- 输出：`outputs/ac3d_matrix_free_single_crop16/matrix_free_single_result.json`

完整 `350^3` 预检命令：

```bash
python scripts/run_ac3d_matrix_free_single.py \
  --frequency 1 \
  --direction x \
  --out-dir outputs/ac3d_matrix_free_full350_preflight \
  --preflight-only
```

预检结果：

- 未知量数：`42,875,000`
- 当前 Python/SciPy/NumPy 矩阵自由原型估计峰值内存：`12.857606634497643 GiB`
- 本机总内存：`8.0 GiB`
- `memory_preflight_passed = false`
- 输出：`outputs/ac3d_matrix_free_full350_preflight/matrix_free_single_preflight.json`

结论：

当前 Python/SciPy 矩阵自由 Krylov + Jacobi 版本已经验证了算法等价性，但不能在这台 8 GB 内存机器上安全运行完整 `350^3`。如果要完整求解，需要改成更低内存的 native streaming solver，或换用至少 32 GB、最好 64 GB 以上内存的机器运行。
