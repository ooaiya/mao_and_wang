# Codex 实验执行汇报

`mxt_codex` 从重新建立的 `mxt` 分支创建，专门保存 Codex 根据实验 Prompt 执行后的汇报、Prompt 对应结果摘要、问题分析和交接材料。

本分支不承担正式代码开发；正式代码修改仅在 `mxt` 分支进行。

仅提交经过整理的文字汇报与必要说明，不提交实验结果文件、采集曲线、原始数据、素材、运行日志或虚拟环境。汇报应记录 Prompt、代码提交、执行范围、验证结论、问题与后续事项，并以本地路径引用原始证据。

`main` 为只读基准，禁止推送、删除或重写。

## 最新交付：2026-11-27

[应用清理、Table十轮审计与Krita素材准备](maintenance/pre_krita_20261127_141145/README.md)：清理完成；Table需要重采；Krita因指定原始ORA缺失而未启动采集。

## Krita合成素材单轮尝试

[2026-11-27素材验收与安全停止报告](foreground_krita/generated_20261127_154636/README.md)：素材和预检通过，唯一采集因持续全局PSI安全停止，PILOT_INVALID。

## 2026-11-27 PSI专项诊断

[全局内存PSI Full只读归因报告](diagnostics/psi_full_root_cause_20261127/README.md)：确认回收与少量换页，责任线程证据不足；100GiB设备已识别，分区/文件系统尚未扩展。
