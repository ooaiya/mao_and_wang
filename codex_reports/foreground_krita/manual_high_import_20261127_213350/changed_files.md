# 修改文件清单

代码基准 `6ce22767fdd91ea23d1e4fab0f071a19c44ea92a` → 本地代码提交 `bc8018ac6d2edb0bda077b23818b7247a2343c67`，共12个文件。以下是源码变更路径；本报告分支没有同步这些可执行文件。全部新增/修改内容均可在[完整Markdown diff](git_diff.md)审核。

| 源码文件 | 类型 |
|---|---|
| `前台操作/前台操作自动化脚本采集/MANUAL_HIGH_IMPORT.md` | 新增 |
| `前台操作/前台操作自动化脚本采集/README.md` | 修改 |
| `前台操作/前台操作自动化脚本采集/configs/collection.rapid-9000-manual-high-import.json` | 新增 |
| `前台操作/前台操作自动化脚本采集/oomlab_krita_collect/cli.py` | 修改 |
| `前台操作/前台操作自动化脚本采集/oomlab_krita_collect/config.py` | 修改 |
| `前台操作/前台操作自动化脚本采集/oomlab_krita_collect/engine.py` | 修改 |
| `前台操作/前台操作自动化脚本采集/oomlab_krita_collect/environment.py` | 修改 |
| `前台操作/前台操作自动化脚本采集/oomlab_krita_collect/manual_import.py` | 新增 |
| `前台操作/前台操作自动化脚本采集/oomlab_krita_collect/pilot_assets.py` | 修改 |
| `前台操作/前台操作自动化脚本采集/oomlab_krita_collect/validation.py` | 修改 |
| `前台操作/前台操作自动化脚本采集/scripts/krita_auto.py` | 修改 |
| `前台操作/前台操作自动化脚本采集/tests/test_manual_import.py` | 新增 |

`krita_accessibility.py`已检查并直接复用其只读快照，无需修改。新配置与原VM部署配置只增加人工导入开关；历史配置、素材和采集数据不覆盖。
