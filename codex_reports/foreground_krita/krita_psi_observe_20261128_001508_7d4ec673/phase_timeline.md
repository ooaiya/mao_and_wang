# 阶段时间线

批次 `krita_psi_observe_20261128_001508_7d4ec673`，run ID `f04ca1afb5da4fffac37c7e1d3c0d292`。代码 `4fbc49555484055bf78f2b6d437b6a04c791dd9f`，配置 SHA256 `8d487b076463470474d3c102dcc269e255b81fc74038faf2d7dd6bba795c6cd0`。

| 事件 | 单调时钟 ns | 相对时间 |
| --- | --- | --- |
| PRE_IMPORT_REVIEW_START | 26589894182330 | 39.322910 s |
| PRE_IMPORT_REVIEW_DONE | 26619894914768 | 69.323642 s |
| HIGH_DOCUMENT_MANUAL_IMPORT_START | 26620069155059 | 69.497883 s |
| HIGH_DOCUMENT_USER_READY | 27142641774096 | 592.070502 s |
| HIGH_DOCUMENT_MACHINE_VERIFY_START | 27142689506476 | 592.118234 s |
| HIGH_DOCUMENT_MACHINE_VERIFY | 未记录 | 未取得 |
| HIGH_DOCUMENT_READY | 未记录 | 未取得 |
| CAPTURE_WINDOW_START | 未记录 | 未取得 |
| CAPTURE_WINDOW_DONE | 未记录 | 未取得 |
| HIGH_INSTANCE_EXIT | 未记录 | 未取得 |
| KRITA_POST_PROCESS | 未记录 | 未取得 |
| TAIL_DOCUMENT_OPEN_DONE | 未记录 | 未取得 |
| POST_CLOSE_REVIEW_START | 未记录 | 未取得 |
| POST_CLOSE_REVIEW_DONE | 未记录 | 未取得 |
| KRITA_EXIT | 未记录 | 未取得 |

| 阶段 | 名称 | 状态 | 结束 | 诊断 |
| --- | --- | --- | --- | --- |
| 1 | 启动Krita | PASS | 13.346789 s |  |
| 2 | 核对主窗口布局 | PASS | 13.432715 s |  |
| 3 | 打开素材文件 | PASS | 38.463571 s |  |
| 4 | 缩放画布 | PASS | 69.323762 s |  |
| 5 | 打开预组装多图层文档 | FAILED | 592.326869 s | RuntimeError('xdotool exit=1: XGetWindowProperty[_NET_ACTIVE_WINDOW] failed (code=1)\nxdo_get_active_window reported an error') |
