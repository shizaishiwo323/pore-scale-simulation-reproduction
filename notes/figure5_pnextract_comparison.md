# Figure 5 孔网提取对比记录

日期：2026-05-20

## 结论

阶段 3 已完成：已使用 `pnextract` 对完整 `350^3` Berea microCT 派生输入提取孔隙网络，并与论文 `Figure5.xlsx` 的孔节点尺寸分布和孔喉长度分布完成对比。

总体判断：

- 孔节点尺寸分布复现较好，主峰位置一致，体积加权平均值接近论文 Figure 5。
- 孔喉长度分布主峰量级一致，但本次 `pnextract` 输出整体偏向更长孔喉，需在后续极化模型中记录为差异来源。

## 输入与命令

完整运行输入：

- `experiments/berea_pnextract/full_350/Berea350_full.mhd`

该输入使用阶段 2 生成的派生 raw：

- `experiments/berea_pnextract/Berea350_pore0_solid1.raw`

运行命令：

```bash
cd experiments/berea_pnextract/full_350
../../../pnextract/bin/pnextract Berea350_full.mhd > Berea350_full.log 2>&1
```

为了减少不必要的大文件，本次完整运行关闭了 `write_elements` 和 `write_vtkNetwork`，只保留 Figure 5 对比所需的 `node/link` 网络文件。

## pnextract 输出

输出目录：

- `experiments/berea_pnextract/full_350/`

核心输出：

- `Berea350_full_node1.dat`
- `Berea350_full_node2.dat`
- `Berea350_full_link1.dat`
- `Berea350_full_link2.dat`
- `Berea350_full.log`

日志摘要：

```text
Berea350_full
***  2126-2 pores, 3849 throats,   ratio: 1.81557  ***
end
```

解析后内部孔数为 `2124`，孔喉数为 `3849`。日志中的 `2126-2` 包含两个边界元素。

## 解析与对比脚本

新增脚本：

- `scripts/parse_pnextract_network.py`
- `scripts/compare_figure5_network.py`

解析命令：

```bash
scripts/parse_pnextract_network.py \
  --prefix experiments/berea_pnextract/full_350/Berea350_full \
  --outdir outputs/figure5_pnextract_comparison/network_parsed
```

对比命令：

```bash
scripts/compare_figure5_network.py \
  --network-dir outputs/figure5_pnextract_comparison/network_parsed \
  --figure5 论文数据/Figure5.xlsx \
  --outdir outputs/figure5_pnextract_comparison \
  --figure-out figures/figure5_pnextract_comparison.png
```

## 对比图与数据

图：

![Figure 5 pnextract comparison](/Users/wangbin/Documents/Codex/论文复现/figures/figure5_pnextract_comparison.png)

数据：

- `outputs/figure5_pnextract_comparison/network_parsed/pores.csv`
- `outputs/figure5_pnextract_comparison/network_parsed/throats.csv`
- `outputs/figure5_pnextract_comparison/network_parsed/network_summary.json`
- `outputs/figure5_pnextract_comparison/figure5_pnextract_comparison.csv`
- `outputs/figure5_pnextract_comparison/figure5_pnextract_metrics.json`

## 数值摘要

pnextract 网络摘要：

| 指标 | 值 |
| --- | ---: |
| 内部 pores | 2124 |
| throats | 3849 |
| pore radius volume-weighted mean | `2.4849e-05 m` |
| throat length volume-weighted mean | `3.8700e-05 m` |
| pore radius range | `3.4078e-06` to `4.5255e-05 m` |
| throat length range | `9.2485e-07` to `1.0275e-04 m` |

Figure 5 对比指标：

| 分布 | L1 distance | paper weighted mean | pnextract weighted mean | paper peak | pnextract peak |
| --- | ---: | ---: | ---: | ---: | ---: |
| pore node size | 0.1495 | `2.4486e-05 m` | `2.4857e-05 m` | `3.3972e-05 m` | `3.3972e-05 m` |
| pore throat length | 0.6396 | `2.6836e-05 m` | `3.8851e-05 m` | `3.5291e-05 m` | `4.3147e-05 m` |

## 列定义与假设

对比时采用：

- `node2.dat` 的 `pore_radius_m` 作为 pore node size，并用 `pore_volume_m3` 加权。
- `link2.dat` 的 `throat_length_m` 作为 pore throat length，并用 `throat_volume_m3` 加权。
- `Figure5.xlsx` 中的 relative volume 在对比前归一化为总和 1。

额外检查：

- 若使用 `link1.dat` 的 pore center-to-center length，与 Figure 5 孔喉长度分布差异更大：
  - L1 distance 为 `1.4019`
  - 体积加权均值为 `7.1498e-05 m`
- 因此后续优先采用 `link2.dat` 的 `throat_length_m` 作为论文膜极化公式中的孔喉特征长度候选。

## 差异解释

孔节点尺寸分布与论文数据吻合较好，说明标签映射、体素尺度和基本 maximal-ball 孔节点识别是合理的。

孔喉长度分布偏长，可能来自：

- 当前 `pnextract` 是 Dong-Blunt 算法的开源重写，不一定与论文作者使用的具体实现和参数完全一致。
- `pnextract` 的孔喉长度定义和论文 Figure 5 中的孔喉长度统计定义可能不完全相同。
- 论文可能使用了额外的图像平滑、分割后处理或网络清理参数。
- 本次未加入 `direction z` 或其他方向变换；不过方向变换理论上不应显著改变长度分布。

后续在阶段 4 计算膜极化时，应优先使用论文 `Figure5.xlsx` 作为严格复现输入；再使用本次 `pnextract` 输出作为“从 microCT 自动提取”的独立路线，比较两者对 `Delta sigma*_w` 和最终 Figure 6-8 的影响。

