# pnextract 本机构建记录

日期：2026-05-20

## 结论

阶段 1 已完成：`pnextract` 已在本机 macOS/arm64 上编译并通过小型网络提取烟雾测试。

可执行文件：

- `pnextract/bin/pnextract`
- `pnextract/build/local/pnextract`

本机构建脚本：

- `scripts/build_pnextract_local.sh`

## 背景

仓库默认 `make -j` 构建没有直接通过，原因是默认构建链会先构建 bundled `zlib`/`libtiff`，并使用偏 Linux 静态链接的 toolchain。

已观察到的问题：

- 现代 CMake 对 bundled `zlib` 的旧 `cmake_minimum_required` 策略报错。
- 加入 `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` 后，默认 toolchain 仍强制 Linux/static，在 macOS 上链接测试失败，错误涉及 `crt0.o` 缺失。

本阶段先采用本机 `g++` 直接编译 `pnextract` 核心源码，禁用 zlib/tiff/OpenMP 相关宏。因此当前二进制支持未压缩 `.raw`/`.mhd` 输入，适合读取本项目的 `microCT_Berea.raw`。

## 构建命令

推荐使用脚本：

```bash
scripts/build_pnextract_local.sh
```

脚本核心命令：

```bash
/usr/bin/g++ -std=c++17 -O2 -Wall -pedantic \
  -DRELEASE_DATE='"2026.05.20-local"' \
  -D_FILE_OFFSET_BITS=64 \
  -Ipnextract/src/include \
  -Ipnextract/src/libvoxel \
  -Ipnextract/src/pnm/pnextract \
  pnextract/src/pnm/pnextract/blockNet.cpp \
  pnextract/src/pnm/pnextract/nextract.cpp \
  pnextract/src/pnm/pnextract/medialSurf.cpp \
  pnextract/src/pnm/pnextract/writers_vtk.cpp \
  pnextract/src/pnm/pnextract/writers_vxl.cpp \
  pnextract/src/libvoxel/voxelImage.cpp \
  -o pnextract/build/local/pnextract
```

构建后脚本会复制：

```bash
cp pnextract/build/local/pnextract pnextract/bin/pnextract
chmod +x pnextract/bin/pnextract
```

## 编译警告

编译完成，但每个翻译单元都会出现两个历史代码警告：

- `src/include/typses.h:701`：`&` 和 `==` 的优先级警告。
- `src/libvoxel/voxelImageI.h:1772`：局部变量 `count` set but not used。

本阶段未修改上游源码。上述警告未阻止链接，也未影响烟雾测试。

## Usage 验证

命令：

```bash
pnextract/bin/pnextract -h
```

结果：

```text
Pore Network Extraction: pnextract version 2026.05.20-local
Usage:
  pnextract vxlImage.mhd    #  extract network
  pnextract -g vxlImage.mhd # -generate vxlImage.mhd
```

## 烟雾测试

测试目录：

- `pnextract/build/local_smoke/`

测试输入：

- `smoke.raw`：人工生成的 `30^3`、`uint8` 二值图像。
- `smoke.mhd`：指向 `smoke.raw` 的 MHD 头文件。

运行命令：

```bash
cd pnextract/build/local_smoke
../../bin/pnextract smoke.mhd > pnextract_smoke.log 2>&1
```

成功输出：

- `smoke_link1.dat`
- `smoke_link2.dat`
- `smoke_node1.dat`
- `smoke_node2.dat`
- `smoke_VElems.mhd`
- `smoke_VElems.raw`
- `smoke_pores.vtu`
- `smoke_throats.vtu`
- `smoke_throatsBalls.vtu`

日志结尾显示：

```text
smoke
***  4-2 pores, 1 throats,   ratio: -0.5  ***
end
```

说明核心入口、图像读取、孔网提取和网络文件写出均已跑通。这个人工图像很小，网络拓扑只用于 smoke test，不用于物理验证。

## 当前限制

- 当前本机二进制没有启用 zlib，因此不支持 `.raw.gz`。
- 当前本机二进制没有启用 libtiff，因此不支持直接读取 `.tif`。
- 当前本机二进制没有启用 OpenMP，完整 `350^3` Berea 运行可能较慢。

这些限制不阻塞下一阶段，因为本项目的 Berea 数据是未压缩 `.raw`。

