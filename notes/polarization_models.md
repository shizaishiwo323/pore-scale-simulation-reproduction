# 电化学极化模型实现记录

日期：2026-05-20

## 结论

阶段 4 已完成：已实现论文 Equations 9-12、17-21 的孔极化、膜极化和上尺度公式，并生成可供后续 AC3D 阶段读取的频率谱 CSV。

核心实现：

- `src/pore_scale_electrical/polarization.py`
- `tests/test_polarization.py`
- `scripts/compute_polarization_spectra.py`

输出：

- `outputs/polarization_spectra_from_figure5.csv`
- `outputs/polarization_spectra_from_figure5.metadata.json`
- `outputs/polarization_spectra_from_pnextract.csv`
- `outputs/polarization_spectra_from_pnextract.metadata.json`

## 复数符号约定

代码内部采用后续 AC3D 求解器将使用的工程复数形式：

```text
sigma* = sigma_real + i sigma_imag
```

因此 `delta_sigma_w*` 的实部和虚部分别输出到 CSV 中，后续 AC3D 可以直接构造 Python/Fortran/C++ 的复数。

注意：论文文字中也出现 `C* = C' - i C''` 的描述。为避免混淆，本实现将“用于求解器的复数值”作为唯一内部约定；如后续需要与论文图中的损耗符号逐项比对，应在绘图层集中处理符号转换。

## 已实现公式

孔极化：

```text
tau_p = r^2 / (2D)
C*_p = [i omega tau_p / (1 + i omega tau_p)] Sigma_S
C*_P = sum_j w_j C*_p(r_j)
```

膜极化：

```text
tau_m = L^2 / (4D)
Z*_m = Z_dc [1 - eta0 (1 - (1 - exp(-2 sqrt(i omega tau_m))) / (2 sqrt(i omega tau_m)))]
C*_m = 1 / Z*_m - 1 / Z_dc
C*_M = sum_j w_j C*_m(L_j)
```

上尺度：

```text
C* = C*_P + C*_M
Delta sigma*_w = 2 C* / Lambda
sigma*_w = sigma_w + i omega epsilon_w + Delta sigma*_w
```

## 参数

默认参数来自论文 Table 1 和正文：

| 参数 | 值 |
| --- | ---: |
| `Sigma_S` | `1.3e-9 S` |
| `D` | `1.3e-9 m^2/s` |
| `Lambda` | `2.7e-6 m` |
| `eta0` | `0.01` |
| `sigma_w` | `0.043 S/m` |
| `epsilon_w` | `80 epsilon0` |
| `epsilon_s` | `7 epsilon0` |
| `epsilon0` | `8.85e-12 F/m` |

## Figure 5 路线

命令：

```bash
scripts/compute_polarization_spectra.py \
  --source figure5 \
  --figure5 论文数据/Figure5.xlsx \
  --out outputs/polarization_spectra_from_figure5.csv \
  --metadata-out outputs/polarization_spectra_from_figure5.metadata.json
```

结果说明：

- `Figure5.xlsx` 提供孔节点尺寸分布和孔喉长度分布。
- 孔极化可直接由孔节点尺寸分布计算。
- 膜极化公式需要 `Zdc`，而 `Figure5.xlsx` 不包含每个孔喉的半径、截面积或电阻。
- 因此 `outputs/polarization_spectra_from_figure5.csv` 中膜极化列保留为空值，`total` 列等于孔极化结果。
- 这份输出适合作为“论文分布驱动的孔极化基准”，不应被解释为完整膜极化复现结果。

## pnextract 路线

命令：

```bash
scripts/compute_polarization_spectra.py \
  --source pnextract \
  --network-dir outputs/figure5_pnextract_comparison/network_parsed \
  --out outputs/polarization_spectra_from_pnextract.csv \
  --metadata-out outputs/polarization_spectra_from_pnextract.metadata.json
```

结果说明：

- 孔极化使用 `pores.csv` 中的 `pore_radius_m`，并用 `pore_volume_m3` 加权。
- 膜极化使用 `throats.csv` 中的 `throat_length_m`。
- `Zdc` 由 pnextract 孔喉几何近似：

```text
G = R^2 / (4A)
A = R^2 / (4G)
g_dc = sigma_w A / L
Zdc = 1 / g_dc
```

这条路线能生成带膜极化的物理量估计，可供后续 AC3D 原型使用；但它继承了阶段 3 中 pnextract 孔喉长度偏长的问题，应作为自动提取路线而非论文严格曲线的唯一依据。

## 测试

命令：

```bash
PYTHONPATH=src pytest -q tests/test_polarization.py
```

结果：

```text
4 passed
```

测试覆盖：

- 孔极化低频极限为 0。
- 孔极化高频极限趋近 `Sigma_S`。
- 膜极化低频扰动为 0。
- 膜极化高频扰动趋近 `eta0 / (1 - eta0) / Zdc`。
- Equation 12 上尺度关系。
- pnextract shape factor 的面积反算。

## 后续注意

- 如果需要严格复现论文膜极化曲线，需要找到作者使用的完整孔喉几何或改版代码中的 `Zdc` 计算细节。
- 阶段 5 中 AC3D 求解器应优先读取 `delta_sigma_total_real_s_m` 和 `delta_sigma_total_imag_s_m`，构造水相 `sigma*_w`。
- 对 Figure 5 路线，因缺少 `Zdc`，阶段 5 应只使用其孔极化部分，或显式标注膜极化为未计算。

