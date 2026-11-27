# 低–高–中前台素材

下载 `krita-ora.zip`，在项目根目录用 `python3 -m zipfile -e /path/to/krita-ora.zip .` 解压。从本目录运行 `sha256sum -c SHA256SUMS`，再将 `OOM_assets/` 部署到 Ubuntu VM 的 `$HOME/OOM_assets/`。只交付前台文件夹时，取压缩包内 `前台操作/素材/OOM_assets/` 的内容并保留子目录层级。[素材 Release](https://github.com/ooaiya/mao_and_wang/releases/tag/repro-assets-v1) · [校验清单](SHA256SUMS)

| 文件 | 场景与尺寸 |
| --- | --- |
| `krita_rapid_9000_46/light_9000.ora` | 低压，9000×9000，1 层 |
| `krita_rapid_9000_46/layered_9000_46.ora` | 高压，9000×9000，46 层 |
| `krita_rapid_9000_tail_07_medium/layered_9000_07.ora` | 中压，9000×9000 画布，五个 9000² 图层和两个 5400² 图层 |

中压素材目录还附有生成时保留的同源轻量 ORA。当前三阶段自动化读取表中的三个 ORA。配置和运行命令见 [前台运行](../前台操作自动化脚本采集/README.md)。
