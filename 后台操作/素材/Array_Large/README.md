# Array Large 原始素材

> 素材类型：**Array 数组操作素材（Large）**  
> 操作 ID：`array_processing`  
> 数据集 ID：`array-2c9c616d2ddec346b783862b`

本目录保存从 Ubuntu 虚拟机旧仓库恢复的 Array Large 样本配置与清单：

- `parameters.json`：数组工作负载参数及算法标识。
- `manifest.json`：样本生成完成标记、配置哈希、参数文件 SHA-256 和理论数组容量。

## 原始配置

| 参数 | 值 |
|---|---:|
| 算法 | `resident-f64-pcg64-v1` |
| 数组数量 | 3 |
| 每个数组元素数 | 90,000,000 |
| 数据类型 | `float64` |
| 分块元素数 | 1,000,000 |
| 随机种子 | 20261026 |
| 理论数组总容量 | 2,160,000,000 Bytes |

## 重要说明

1. 这是 **Array 数组操作素材**，不是 XZ、Table 或图像处理素材。
2. 该工作负载由程序在内存中生成并驻留三个 NumPy `float64` 数组；本目录中的 JSON 是参数文件和样本清单，不是三个数组的二进制转储文件。
3. `manifest.json` 中记录的参数文件 SHA-256 用于核验 `parameters.json` 是否与原始样本一致。
4. 历史十轮采集结果不放在 GitHub。本目录只保存可复现该 Large 样本所需的配置素材；十轮原始结果、每轮 metadata 和恢复报告单独归档到本地/网盘，供后续三线并发实验引用。
5. 来源：虚拟机旧仓库 `~/OOM_before_clone_20261104_115352/work/kernel61712-array-processing/large/data/`，恢复时核对了原始 `parameters.json` 与 `manifest.json` 内容。

