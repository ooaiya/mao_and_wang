# 历史证据盘点

> 发布说明：本次依据用户随后“报告传到github的mxt_codex”的授权，仅发布Markdown报告。文中不提交/推送的限制描述此前只读诊断阶段。原始数据、CSV、日志、JSON与PNG留在VM。

首先逐文件计算SHA256并核对原manifest.sha256，通过37个封存成员；实际成员集合也完全匹配。此后仅在新diagnostics目录写派生文件，未修改原run。

|文件|状态|字节|SHA256|
|---|---|---:|---|
|assets_manifest.after.json|已验证|2757|`81afbf5571a5cb8151f2adb66345251581e80435663757b4502d712e0a31e7f6`|
|assets_manifest.json|已验证|2757|`81afbf5571a5cb8151f2adb66345251581e80435663757b4502d712e0a31e7f6`|
|automation.log|已验证|23171|`04ace000158cbd02b37e8a0235160ebfb7243afc898a66cb28138789c451f052`|
|boundary.json|已验证|712|`c8acb25f97731e3f90a4badccf02b367c6890f366b417910abf8bfbe52f6a78a`|
|cgroup-end.json|已验证|7613|`13e669e01bf1c47a9573370201c0ca86cb2e871b764a081e4cc91707114ce1b5`|
|cgroup-observations.jsonl|已验证|325709|`94749478b3236611e3fb6fa2bc8556603c95c16e4bb3e653987fabd1337e7a00`|
|cgroup-start.json|已验证|7419|`6b49ccf1e449e0a9099b2b13bfb01062180d8d770dd8f7bf047eab58d2b79bfc`|
|cleanup.json|已验证|2385|`0d9e8adc5d87929b17baf57f966076e79b4551a3578c5f41fe41287e5dbcc22d`|
|config.snapshot.json|已验证|2994|`ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d`|
|cooldown.jsonl|已验证|548141|`b0cf349939889522f7ab4262855e859a79f8b6c4d5542090398c08e404c6ec9e`|
|environment.json|已验证|11846|`36036caf411cba88f87c626e88751b8efd720504f71e56f1293395d4cfaa53ef`|
|hold/ready.json|已验证|88|`f712d502667c258b007b5239721935ae1f487c4d24cd72e85eb6cdf5fc8bedec`|
|hold/systemd-start.json|已验证|2069|`80ccbd6533d0f8e2c1de3c034fd27e9877b46ac7a076f391ec2e88ed78abf064`|
|hold/unit-identity.json|已验证|981|`dbd5a92da139f6b94ca672b20dc23022d0d00dbd41c16eff526b295789607a6d`|
|journal.log|已验证|61971|`097215f3b6d53d3b6966843b67fbd9affe401f914728c197be59df02da9d1fda`|
|krita/automation.log|已验证|23133|`1715d197fcd35faa3f2c62d6b01697dd63ed6e254d64c181bca6c52d23be7853`|
|krita/command.json|已验证|2582|`4c0f084a72e1900e2682f59f0c85e002bec97d04bbccb58f5ccd434da9610143`|
|krita/finished.json|已验证|210|`0064b9e313738ab4e615deabf12b8637258b62d7d5719003bcdf1e80e1fc7d1a`|
|krita/go.json|已验证|67|`23e096c8449d7d830242a166ae4c497bf97e62e39015cfa3f6e6e4b44ff0a6ce`|
|krita/isolated-krita-config/QtProject.conf|已验证|722|`f5f7fb885b7a5b5e0e0909bbad529eead568135e2bdab8cb47ac64fcde771e4d`|
|krita/isolated-krita-config/kritadisplayrc|已验证|33|`e0d9d4b5671e471e591bef6d3f130e28f8caaee4b435408d5e413e3c436f362e`|
|krita/isolated-krita-config/kritarc|已验证|11071|`d583dd25957e51a7e8acacdb03803c2986bc0d8943a3c70f1729e8e3faa028bc`|
|krita/krita-process.json|已验证|1006|`354fda81a233aeaf2dc81b4c76362ae27371e411c7d6260cf55e869d44df8849`|
|krita/phase-events.jsonl|已验证|18515|`c44243c8eef9f84f2fb0182c8f6216647139877a450b9c8beaaa502b8cd81f6e`|
|krita/ready.json|已验证|89|`f5dc6c731a9f881f6148823e46bbb5ab7cc3e2e0271bae4972caccbe9a83a234`|
|krita/started.json|已验证|129|`e7c288793813ed512904a1212fe39a836a4a2fae60a019fbf48c31502c9291b7`|
|krita/systemd-start.json|已验证|2058|`b7f12503d0788916be71ea5f4e4ab0d3f9800e2c1e5e3986061004b1f38d4a24`|
|krita/unit-identity.json|已验证|986|`0e05f1892a52e33c53f5a1ccb7deedd65f0946ddabf0d94df652f9b8aaa97230`|
|krita/workload-pid.json|已验证|72|`81d44b59f0fe334b7463d8346e332fff9335eede8af56be15d71daad8dddbe19`|
|memory-events.jsonl|已验证|753|`b59fa8e307875a6d4a8036324a2104bbb24cacf5960da2ccb90847b2b8749d9f`|
|metadata.json|已验证|25122|`1438b9e81859f2caeaf9669f48bf9d3f83caeb227789dab2bf190890f728380c`|
|phase-events.jsonl|已验证|18594|`afff97b0f63a9bb1e22b99e08b0464c79bac01deed1e2d5d052f44653c03fb60`|
|process-observations.jsonl|已验证|1159257|`2c0afdc788869f9293a4cdf4a0bd0d0b783d4e8d2b5ef1803bb89692d169dc45`|
|report.md|已验证|7933|`1a43253898a6157e84ebbd2cb4c19e55598bc5cedd311ec6a0b35a28ad55c185`|
|samples.csv|已验证|15769962|`1ba65790336923d7f62fae92247a70254bf308a6e647fa7b5b4bf3e34abacf0f`|
|stop-request.json|已验证|7828|`4f0ff147ce567bd43d2428fa2915856be2461889a4eac0dfa88ca4898e0e5bc6`|
|summary.json|已验证|3707|`1b042274cf43b985d7638bcf31d616f167ea549cd981d526faa94a9f71a75d38`|

remaining-processes.json不存在，标记UNKNOWN，不能补造。其余请求的samples、metadata、environment、config、cgroup起止/过程、进程、memory-events、phase、automation、journal均存在。

旧boot f6f5422e-c9e9-4efe-bdf8-2f8f3844b6c2；当前boot b0f8e49f-ad03-4e9e-ac35-b44d54a4ee14。current/kernel_history.txt最初只查询当前boot无条目；已纠正为current/kernel_historical_boot.txt，显式查询旧boot同一时间窗，仍无条目。历史system journal存在，主要为本次自动化及GNOME窗口事件；内核无日志不能证明没有回收，回收增量由vmstat证明。

历史全机Cached/Buffers/SReclaimable/SUnreclaim/Active/Inactive/Dirty/Writeback未逐样本保存，UNKNOWN；samples里的stat_*仅为cgroup指标。当前完整meminfo不能回填历史。zswap/zram、zone水位、compaction/THP、宿主机压力/balloon历史指标同样UNKNOWN。
