# 阶段时间线

批次 `krita_three_guard_20261128_010241_2cb959a6`，run ID `717be1060cc54a55ae1c93d0dee082f8`。代码 `715afeaf0644d35da3cb207ab211dbaa85f75b6a`，配置 SHA256 `c6b19c657518b3ca754f7dd4474e973c878bc590183d60fb37fa89c7bd88b6f5`。

| 事件 | 单调时钟 ns | 相对时间 |
| --- | --- | --- |
| PRE_IMPORT_REVIEW_START | 29351142951991 | 29.762113 s |
| PRE_IMPORT_REVIEW_DONE | 29381143854583 | 59.763015 s |
| HIGH_DOCUMENT_MANUAL_IMPORT_START | 29381281001217 | 59.900162 s |
| HIGH_DOCUMENT_USER_READY | 未记录 | 未取得 |
| HIGH_DOCUMENT_MACHINE_VERIFY_START | 未记录 | 未取得 |
| HIGH_DOCUMENT_MACHINE_VERIFY | 未记录 | 未取得 |
| HIGH_DOCUMENT_READY | 未记录 | 未取得 |
| CAPTURE_WINDOW_START | 未记录 | 未取得 |
| CAPTURE_WINDOW_DONE | 未记录 | 未取得 |
| HIGH_INSTANCE_EXIT | 未记录 | 未取得 |
| KRITA_POST_START | 未记录 | 未取得 |
| KRITA_POST_PROCESS | 未记录 | 未取得 |
| TAIL_DOCUMENT_OPEN_DONE | 未记录 | 未取得 |
| POST_CLOSE_REVIEW_START | 未记录 | 未取得 |
| POST_CLOSE_REVIEW_DONE | 未记录 | 未取得 |
| KRITA_EXIT | 未记录 | 未取得 |

| 阶段 | 名称 | 状态 | 结束 | 诊断 |
| --- | --- | --- | --- | --- |
| 1 | 启动Krita | PASS | 11.602145 s |  |
| 2 | 核对主窗口布局 | PASS | 11.684435 s |  |
| 3 | 打开素材文件 | PASS | 28.953933 s |  |
| 4 | 缩放画布 | PASS | 59.763086 s |  |
| 5 | 打开预组装多图层文档 | STOPPED | 67.254058 s | StopRequested('RuntimeError: 50ms sampler gap exceeded safety bound') |
