# 后台任务素材

`oom_data/` 与自动化运行器读取的 `~/oom_data` 布局相同。

| 目录 | 输入 |
| --- | --- |
| `xz_large/` | 单线程 128 MiB 字典档位的 1792 MiB `input.bin` 和 `manifest.json` |
| `table_large/` | 800 万行 `table.csv` 和带预期统计的 `manifest.json` |
| `array_large/` | 原实验 VM 的 `parameters.json` 和 `manifest.json`，工作进程按种子生成三个数组 |
| `xz_small/` | 原实验 VM 的 256 MiB 小样本，供轻量检查 |

Large XZ 和 Table 由相同生成代码重建并与原实验逐字节摘要核对，Array 沿用原文件。Linux 下可在本目录运行 `sha256sum -c SHA256SUMS` 检查传输完整性。 `Array_Large/` 保存此前归档的参数和来源说明。

栅格任务的输入按种子在执行时构造。正式用 `--side 18432 --sweeps 745`，源码使用种子 `20261116`，参考尺寸、环境、输出统计与曲线见 [栅格频域独立采样](../../实验结果/栅格频域独立采样_20261116/results/)。

正式对照所需的四项任务输入均可从交付目录复现。XZ/表格/数组的其他档位由 `后台操作/configs/profiles.json` 和准备入口生成，参见 [后台操作](../README.md)。
