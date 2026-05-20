# Berea microCT 数据与 pnextract 输入审计

日期：2026-05-20

## 结论

阶段 2 已完成：已为 `pnextract` 准备 Berea 输入，并确认标签 `1` 应作为孔隙/水相、标签 `2` 应作为固相。

用于后续完整孔网提取的输入文件：

- `experiments/berea_pnextract/Berea350.mhd`
- `experiments/berea_pnextract/Berea350_pore0_solid1.raw`

生成脚本：

- `scripts/prepare_berea_pnextract_input.py`

标签审计脚本：

- `scripts/audit_berea_raw_labels.py`

审计输出：

- `outputs/berea_label_check/berea_label_stats.csv`
- `outputs/berea_label_check/berea_label_center_slices.png`

## 原始 raw 基本信息

原始数据：

- `论文数据/microCT_Berea.raw`

读取设定：

- shape: `350 x 350 x 350`
- dtype: little-endian `uint16` (`<u2`)
- 原始文件大小：`85,750,000` bytes，等于 `350^3 * 2`

标签统计：

| label | voxel count | volume fraction | 6-connected components | largest component / label | largest component touches all faces |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 9,924,264 | 0.2314697143 | 273 | 0.9990868844 | yes |
| 2 | 32,950,736 | 0.7685302857 | 432 | 0.9999162993 | yes |

判断：

- 论文 Berea 样品孔隙率为 `20.2%`。
- 标签 `1` 的体积分数为 `23.15%`，与孔隙率处于同一量级。
- 若将标签 `2` 解释为孔隙，则孔隙率会是 `76.85%`，不符合 Berea 砂岩物理含义。
- 因此本项目后续采用：`label 1 = pore/water`，`label 2 = solid`。

## 中心切片核对

切片图：

![Berea label center slices](/Users/wangbin/Documents/Codex/论文复现/outputs/berea_label_check/berea_label_center_slices.png)

图中上排为 label 1 mask，下排为 label 2 mask。label 1 呈少量连通孔隙空间，label 2 为主体骨架；这与 Berea 砂岩二值图像的相比例相符。

## pnextract 输入准备

`pnextract` 约定：

- 孔隙/void voxels 必须为 `0`
- 固相 voxels 为非零

最初尝试让 `pnextract` 直接读取 `MET_USHORT` 原始 raw，并在 `.mhd` 中用 `replaceRange 1 1 0`、`replaceRange 2 2 1` 做映射。但实际运行发现当前 `pnextract` 主流程的 `VImage` 需要 `unsigned char` 图像，`MET_USHORT` 会在 `readConvertFromHeader` 转换处失败。

因此采用更稳妥的派生输入：

- 原始 `uint16` raw 保持只读。
- 生成 `uint8` raw：`Berea350_pore0_solid1.raw`。
- 映射关系：
  - `1 -> 0`，孔隙/水相
  - `2 -> 1`，固相

派生输入大小：

- `42,875,000` bytes，等于 `350^3 * 1`

派生输入统计：

| value | meaning | voxel count | volume fraction |
| --- | --- | ---: | ---: |
| 0 | pore/water | 9,924,264 | 0.2314697143 |
| 1 | solid | 32,950,736 | 0.7685302857 |

## 主输入文件

`experiments/berea_pnextract/Berea350.mhd` 内容要点：

```text
ObjectType = Image
NDims = 3
ElementType = MET_UCHAR
ElementByteOrderMSB = False
DimSize = 350 350 350
ElementSize = 2.8 2.8 2.8
Offset = 0 0 0
ElementDataFile = Berea350_pore0_solid1.raw

title Berea350
write_elements true
write_vtkNetwork true
```

注意：`ElementSize = 2.8 2.8 2.8` 会被 `pnextract` 识别为微米并自动转为 SI 单位。

## pnextract 读取测试

为避免直接进入完整 `350^3` 孔网提取，本阶段运行了一个中心 `80^3` 裁剪体读取测试：

- 输入：`experiments/berea_pnextract/Berea350_crop80_readcheck.mhd`
- 日志：`experiments/berea_pnextract/Berea350_crop80_readcheck.log`

运行命令：

```bash
cd experiments/berea_pnextract
../../pnextract/bin/pnextract Berea350_crop80_readcheck.mhd > Berea350_crop80_readcheck.log 2>&1
```

成功输出：

- `Berea350_crop80_readcheck_link1.dat`
- `Berea350_crop80_readcheck_link2.dat`
- `Berea350_crop80_readcheck_node1.dat`
- `Berea350_crop80_readcheck_node2.dat`
- `Berea350_crop80_readcheck_VElems.mhd`
- `Berea350_crop80_readcheck_VElems.raw`

日志结尾：

```text
Berea350_crop80_readcheck
***  49-2 pores, 63 throats,   ratio: 1.46512  ***
end
```

说明 `pnextract` 已能正确读取派生 Berea 输入并生成网络文件。完整 `350^3` 提取留到阶段 3。

## 当前限制与后续注意

- 标签语义已足够支持下一阶段；但与论文实测孔隙率 `20.2%` 的差异需要在后续 Figure 5 对比中继续记录。
- 目前未判断是否需要 `direction z` 或其他方向变换；这应在 Figure 5 分布和后续有效电学性质对比中再决定。
- 派生 raw 是生成文件，可重复创建；原始 `论文数据/microCT_Berea.raw` 未被修改。

