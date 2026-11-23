# 串行曲线离线规划器

`src/` 和 `tools/oracle_plan.cpp` 来自原 memshiftd B/C 工程。这里保留七个源文件，编译为一个计算离线时间表的命令行程序。用于 `segmented_runner.py --serial-policy offline --planner <程序路径>` 的前台退出后续跑规划。运行时冻结和解冻由 Python 执行器控制。

在 Ubuntu 安装 g++ 后，从项目根目录运行 `bash 冻结并发/离线规划器/build.sh`。曲线分级、仅冻结和基线入口直接使用 Python。
