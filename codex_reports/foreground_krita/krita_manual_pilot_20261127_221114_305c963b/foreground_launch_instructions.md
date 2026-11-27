> 归档启动记录：本批次已执行一次并因PSI安全守卫停止，原验证器为PILOT_INVALID。以下是启动前交接原文，不代表当前仍待启动；请勿重新执行命令。

# 人工导入单轮前台启动交接

状态：AWAITING_USER_FOREGROUND_TERMINAL；尚未运行原preflight/collect，无run ID。Codex工具stdin不是TTY，按用户附件第五节停止工具启动；没有创建伪终端。

计划批次：`krita_manual_pilot_20261127_221114_305c963b`。代码与配置、素材指纹核对通过，VM只读快照PASS。真实前台启动时会再次执行原GUI preflight，只有通过才执行原collect一次及原validate。

在VM GNOME Terminal直接前台运行一次：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/mxt/TeamOOM/runtime/venv/bin/python /home/mxt/TeamOOM/results/foreground_krita/krita_manual_pilot_20261127_221114_305c963b/start_once.py
```

不要sudo、nohup、加&或重定向stdin，不要在Codex工具终端运行。此启动脚本位于results目录，不修改仓库代码或配置；不分配PTY、不读/模拟READY。它继承用户真实终端stdin给原CLI，仅转录stdout到本批次日志。独占标记阻止同批次重跑。

提示MANUAL IMPORT REQUIRED后，用已启动Krita打开46层ORA并目视检查，再在该GNOME终端输入READY 46或ABORT。核验完成后HIGH_DOCUMENT_READY起完整12秒，其余流程原样。任何失败都不重新执行命令；返回Codex分析现有记录。

数据目录：`/home/mxt/TeamOOM/data_collection/foreground_krita/krita_manual_pilot_20261127_221114_305c963b`。结果目录：`/home/mxt/TeamOOM/results/foreground_krita/krita_manual_pilot_20261127_221114_305c963b`。
