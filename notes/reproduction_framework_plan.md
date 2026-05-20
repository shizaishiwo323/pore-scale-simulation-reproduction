# 孔隙尺度电学模拟框架复现计划

日期：2026-05-20

## 目标

完整复现 Niu, Zhang, and Prasad (2020) 已实现的孔隙尺度模拟框架，覆盖从 Berea 砂岩二值 microCT 图像、孔隙网络提取、电化学极化上尺度、复数有限差分求解，到 Figure 6-8 曲线对比的全流程。

当前核心资料：

- 主论文：`论文资料/JGR Solid Earth - 2020 - Niu - A Framework for Pore‐Scale Simulation of Effective Electrical Conductivity and Permittivity (1).pdf`
- 补充材料：`论文资料/jgrb54470-sup-0001-2020jb020515-si.docx`
- microCT 数据：`论文数据/microCT_Berea.raw`
- 论文数据表：`论文数据/Figure5.xlsx` 至 `论文数据/Figure8.xlsx`
- 孔网提取代码：`pnextract/`
- AC3D 参考来源：`论文资料/NISTIR 6269.pdf`

## 已确认事实

- `microCT_Berea.raw` 文件大小为 `85,750,000` bytes，匹配 `350 * 350 * 350 * 2`。
- 数据可按 little-endian `uint16` 解释，体素标签仅有 `1` 和 `2`。
- 主论文说明模拟 REV 为 `350^3` 体素，体素边长为 `2.8 um`。
- 论文使用水相 `sigma_w = 0.043 S/m`、`epsilon_w = 80 epsilon0`，固相 `epsilon_s = 7 epsilon0`。
- 表 1 给出 `D = 1.3e-9 m^2/s`、`Lambda = 2.7 um`、`eta0 = 1%`、`Sigma_S = 1.3e-9 S`。
- `Figure5.xlsx` 包含孔节点尺寸分布和孔喉长度分布，可作为孔网提取结果的首要验证基准。
- `Figure7.xlsx` 和 `Figure8.xlsx` 包含模拟曲线，可作为后续数值求解器的基准。

## 总体流水线

1. 准备 Berea microCT 输入。
2. 使用 `pnextract` 提取孔隙网络。
3. 从孔网或 `Figure5.xlsx` 得到孔径/孔喉长度分布。
4. 实现孔极化和膜极化模型，计算 `C*_P`、`C*_M` 和 `Delta sigma*_w`。
5. 实现或改造 AC3D 复数有限差分求解器，计算 `sigma*_eff`。
6. 频率扫描并生成 Figure 6-8 对比图和误差表。

## 阶段 1：编译并跑通 pnextract

状态：已完成，2026-05-20。

完成记录：

- 已新增本机构建脚本：`scripts/build_pnextract_local.sh`。
- 已生成 macOS/arm64 可执行文件：`pnextract/bin/pnextract`。
- 已通过 usage 验证：`pnextract/bin/pnextract -h`。
- 已通过小型人工图像烟雾测试，测试目录为 `pnextract/build/local_smoke/`。
- 烟雾测试成功输出 `smoke_link1.dat`、`smoke_link2.dat`、`smoke_node1.dat`、`smoke_node2.dat` 和 VTK 文件。
- 详细记录见：`notes/pnextract_build_notes.md`。

当前限制：

- 当前二进制未启用 zlib/libtiff/OpenMP，主要支持本项目需要的未压缩 `.raw` 输入。
- 原仓库默认 `make -j` 仍不适合当前 macOS 环境，原因是 bundled zlib/libtiff 和 Linux/static toolchain 配置；后续如需 `.raw.gz`、`.tif` 或并行加速，再单独处理。

目的：在本机得到可执行的 `pnextract`，并能对小型测试图像运行。

已发现问题：

- `make -j` 会先构建 bundled `zlib`，现代 CMake 对旧 `cmake_minimum_required` 报错。
- 加兼容参数后，默认 toolchain 偏 Linux 静态链接，在 macOS 上出现 `crt0.o` 缺失。

计划：

1. 为本机 macOS 编译增加本地构建方式，避免默认 Linux/static toolchain。
2. 优先禁用不必要依赖，先支持未压缩 `.raw` 输入。
3. 编译核心目标：`pnextract`，必要时再编译 `voxelImageProcess`。
4. 运行仓库自带小测试或自建 `20^3` 人工图像测试。

预期产物：

- `pnextract/bin/pnextract` 或等价可执行文件。
- `notes/pnextract_build_notes.md`，记录构建命令、依赖、错误和修复方式。

完成标准：

- 可执行文件能打印 usage。
- 小型测试图像能输出 `*_link1.dat`、`*_link2.dat`、`*_node1.dat`、`*_node2.dat`。
- 不修改、不移动、不覆盖 `论文数据/` 下的原始数据。

## 阶段 2：准备 Berea 的 `.mhd` 输入并确认相标签

目的：让 `pnextract` 正确读取 Berea raw，并确认标签 `1` 是否为孔隙相。

初步判断：

- 标签 `1` 占比约 `23.15%`，标签 `2` 占比约 `76.85%`。
- 论文实测孔隙率为 `20.2%`，二值图像孔隙率可能因裁剪、重采样或分割差异略高。
- 因此标签 `1` 很可能是孔隙/水相，但需要用图像和统计验证，不能只凭占比写死。

计划：

1. 新建 `inputs/` 或 `experiments/berea_pnextract/` 存放 `.mhd`，不放入原始数据目录。
2. 准备只读引用原始 raw 的 `.mhd` 头文件。
3. 在 `.mhd` 中将标签映射为 `pnextract` 约定：
   - 若标签 `1` 是孔隙：`replaceRange 1 1 0`，`replaceRange 2 2 1`。
   - 若标签 `2` 是孔隙：反向映射，并记录证据。
4. 输出若干中间切片或体素统计，用主论文 Figure 3 进行视觉核对。

建议 `.mhd` 草案：

```text
ObjectType = Image
NDims = 3
ElementType = MET_USHORT
ElementByteOrderMSB = False
DimSize = 350 350 350
ElementSize = 2.8 2.8 2.8
Offset = 0 0 0
ElementDataFile = ../../论文数据/microCT_Berea.raw

replaceRange 1 1 0
replaceRange 2 2 1
title Berea350
write_elements true
write_vtkNetwork true
```

预期产物：

- `experiments/berea_pnextract/Berea350.mhd`
- `outputs/berea_label_check/` 中的切片图和统计摘要。
- `notes/berea_raw_data_audit.md` 中记录标签语义、孔隙率和证据。

完成标准：

- `.mhd` 被 `pnextract` 或 `voxelImageProcess` 正确读取。
- 输出孔隙率与标签统计一致。
- 明确记录标签 `1/2` 的物理含义和不确定性。

## 阶段 3：提取孔网并对比 Figure 5

目的：用 `pnextract` 从 Berea microCT 重新提取孔隙网络，并与论文提供的 Figure 5 数据对比。

计划：

1. 先在小裁剪体积上运行，例如 `50^3` 或 `100^3`，验证流程和输出格式。
2. 再运行完整 `350^3`，视内存和耗时决定是否需要分块或更强机器。
3. 解析输出：
   - `*_node2.dat`：孔体积、孔半径、孔形状因子等。
   - `*_link1.dat`：孔喉半径、形状因子、中心到中心长度。
   - `*_link2.dat`：孔喉分段长度、体积等。
4. 将提取结果换算到 SI 单位，与 `Figure5.xlsx` 的两组分布对比：
   - pore node size distribution
   - pore throat length distribution
5. 若差异明显，检查：
   - 标签映射是否反了；
   - 是否需要 `direction z`；
   - 是否需要复现论文的平滑、重采样、裁剪或 segmentation 后处理；
   - `pnextract` 版本是否与论文作者实际使用的 Dong-Blunt 实现不同。

预期产物：

- `experiments/berea_pnextract/run_*/`：每次运行的输入、日志和输出网络。
- `scripts/parse_pnextract_network.py`
- `scripts/compare_figure5_network.py`
- `figures/figure5_pnextract_comparison.png`
- `outputs/figure5_pnextract_comparison.csv`

完成标准：

- 能生成完整孔网文件。
- 能复现 Figure 5 的分布趋势，或明确记录差异来源。
- 每次运行有命令、输入文件、输出路径和参数记录。

## 阶段 4：实现孔极化和膜极化公式

目的：实现论文 Equations 9-12、17-21，得到频率相关的水相附加复电导率 `Delta sigma*_w`。

公式模块：

- 孔极化：
  - `tau_p = r^2 / (2D)`
  - `C*_p = (i omega tau_p / (1 + i omega tau_p)) * Sigma_S`
  - 对孔径分布卷积或加权求和，得到 `C*_P`
- 膜极化：
  - `tau_m = L^2 / (4D)`
  - `Z*_m = Z_dc * [1 - eta0 * (1 - (1 - exp(-2 sqrt(i omega tau_m))) / (2 sqrt(i omega tau_m)))]`
  - `C*_m = 1 / Z*_m - 1 / Z_dc`
  - 对孔喉长度分布卷积或加权求和，得到 `C*_M`
- 上尺度：
  - `C* = C*_P + C*_M`
  - `Delta sigma*_w = 2 C* / Lambda`

计划：

1. 先直接使用 `Figure5.xlsx` 实现论文曲线对应的极化模块。
2. 再切换到 `pnextract` 输出的分布，比较两种输入对 `Delta sigma*_w` 的影响。
3. 明确复数符号约定：论文写法为 `C* = C' - i C''`，AC3D/NIST 代码使用 `cmplx(real, imag)`，需要在转换处集中处理。
4. 保存频率、`C*_P`、`C*_M`、`C*`、`Delta sigma*_w` 的中间表。

预期产物：

- `src/pore_scale_electrical/polarization.py`
- `tests/test_polarization.py`
- `scripts/compute_polarization_spectra.py`
- `outputs/polarization_spectra_from_figure5.csv`

完成标准：

- 低频/高频极限行为符合公式。
- 关键参数全部可配置并有单位说明。
- 输出可直接供 AC3D 求解器读取。

## 阶段 5：实现或改造 AC3D 复数有限差分求解器

目的：解论文 Equation 15，并用 Equation 16 计算有效复电导率 `sigma*_eff`。

可选路线：

1. 从 NISTIR 6269 的 `AC3D.F` 复原 Fortran 代码，再改造成可读入 Berea 图像和频率参数。
2. 用 Python/SciPy 实现 AC3D 等价求解器，先保证正确性，再考虑性能优化。
3. 用 C++/Fortran 重写核心矩阵-向量乘法和共轭梯度，Python 只负责调度和后处理。

建议路线：

- 先采用 Python/SciPy 原型。
- 使用小网格验证边界条件、相电导率、平均电流计算。
- 确认与 NISTIR 小算例或解析串并联结果一致后，再跑 Berea 子体积。
- 全尺寸 `350^3` 视内存和时间决定是否改用 C++/Fortran。

核心实现要点：

- 输入体素相标签，映射到固相和水相。
- 每个频率下：
  - 固相：`sigma*_s = i omega epsilon_s`
  - 水相：`sigma*_w = sigma_w + i omega epsilon_w + Delta sigma*_w`
- 相邻体素 bond conductance 用半格串联调和平均：
  - `be(i,j) = 1 / (0.5 / sigma_i + 0.5 / sigma_j)`
- 周期边界条件。
- 外加平均电场，优先分别求 x、y、z 方向；论文图表可先使用一个方向并记录假设。
- 计算体平均电流 `<J>`，得到 `sigma*_eff = <J> / <E>`。

预期产物：

- `src/pore_scale_electrical/ac3d_solver.py`
- `tests/test_ac3d_solver.py`
- `scripts/run_ac3d_frequency_sweep.py`
- `outputs/ac3d_small_grid_validation/`

完成标准：

- 均匀介质结果等于输入相电导率。
- 简单串联/并联结构结果与解析值一致。
- 小体积 Berea 子样本能稳定收敛并输出复电导率。
- 全尺寸运行前有资源估计和可恢复的运行日志。

## 阶段 6：频率扫描和 Figure 6-8 对比

目的：建立论文图表级别的自动化复现实验。

计划：

1. 定义频率数组，覆盖 `1e-3 Hz` 到 `1e9 Hz`。
2. 对每个频率计算：
   - `Delta sigma*_w`
   - `sigma*_eff`
   - `real conductivity sigma'_eff`
   - `imaginary conductivity sigma''_eff`
   - `real permittivity epsilon'_eff = sigma''_eff / omega`
   - `relative permittivity epsilon'_eff / epsilon0`
3. 分别运行：
   - interfacial only
   - pore polarization only
   - membrane polarization only
   - all polarizations
4. 与 `Figure7.xlsx`、`Figure8.xlsx` 对比。
5. 生成图表、CSV 和误差摘要。

预期产物：

- `experiments/figure6_figure8_reproduction/config.yml`
- `scripts/plot_figure6_figure8_comparison.py`
- `figures/reproduced_figure6.png`
- `figures/reproduced_figure7_or_8.png`
- `outputs/figure6_figure8_metrics.csv`

完成标准：

- 图表包含论文数据、复现数据和误差指标。
- 所有曲线来源、单位、参数和命令可追踪。
- 对无法一致的频段给出原因假设，例如 microCT 分辨率、孔网提取差异、极化模型简化或 AC3D 求解设置差异。

## 依赖与环境

默认 Conda 环境：

```bash
conda activate sip-simpeg
```

当前已知需要补充或确认的依赖：

- `openpyxl`：读取 `.xlsx`。
- `pytest`：测试。
- `pyyaml`：实验配置。
- `scipy`：稀疏线性代数。
- `matplotlib`：绘图。
- 可选：`porespy`、`openpnm`，用于交叉验证孔网提取。

pnextract 构建侧需要：

- C++17 编译器。
- GNU make。
- macOS 本地构建配置，或 Linux 环境/容器。

## 风险与决策点

- `pnextract` 是 Dong & Blunt 算法的开源重写，不一定等于论文作者实际运行的代码版本。
- 论文只给出孔径/孔喉分布和参数，并未给出作者改过的 AC3D 源码。
- `350^3` 复数有限差分求解内存和时间成本较高，必须先小网格验证。
- 标签 `1/2` 的相含义需要证据确认。
- 复数符号约定是高风险点，必须集中封装并用极限情况测试。

## 推荐近期执行顺序

1. 写 `notes/pnextract_build_notes.md`，修通 `pnextract` 本机构建。
2. 新建 `experiments/berea_pnextract/Berea350.mhd`，读取并确认标签语义。
3. 跑 `50^3` 或 `100^3` 裁剪体，解析 `pnextract` 输出。
4. 用 `Figure5.xlsx` 先实现极化公式，避免孔网提取差异阻塞后续。
5. 实现 AC3D Python 原型，通过解析小算例。
6. 做 Figure 6-8 的最小频率扫描，再逐步放大全频率和全尺寸体积。
