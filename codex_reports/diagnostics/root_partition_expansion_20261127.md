# 根分区在线扩容验收

阶段A状态：PASS。仅在本阶段用户明确授权下扩大原分区尾部及在线ext4；未重启、未删除重建分区、未改Swap或内核参数。

|项目|扩容前字节|扩容后字节|
|---|---:|---:|
|虚拟盘/dev/sda|107374182400|107374182400|
|末分区/dev/sda3|85358280704|106834148864|
|根ext4，df总容量|83423059968|104557830144|
|根目录可用|12226023424|32497709056|

可用空间增加20271685632B，约18.879GiB，新增空间的一部分用于文件系统元数据和保留块。原分区开始扇区1054720保持不变；sda1/sda2整条sfdisk记录完全相同，sda3 UUID不变。根直接为ext4，无LVM/LUKS/RAID映射。

本次sgdisk -v已显示No problems found，备份GPT已在100GiB磁盘正确位置，无需再次sgdisk -e。growpart缺失，按附件允许的parted路径执行；lsblk旧版不支持START显示列，起始扇区改由sfdisk JSON和sgdisk -i确认。parted -s对已挂载根分区的确认提示返回非零、没有扩分区；随后正常交互parted对同一resizepart操作确认Yes，exit0。没有强制重新读表。

partprobe成功、udevadm settle成功，blockdev /dev/sda3与分区表字节完全一致后，才执行resize2fs。工具报告online resizing，最终26082555个4KiB块。sgdisk最终验证No problems found；剩余2014个空闲扇区属对齐开销。Swap前后swapon --show --bytes文本相同，约2GiB的/swapfile配置和容量未改。没有对挂载根执行e2fsck。

分区表备份位于 `/home/mxt/TeamOOM/results/maintenance/rootfs_expand_20261127T094238Z`，包括gpt-before.bin、sfdisk-before.txt（dump）、前后lsblk/df、GPT校验、partprobe和resize2fs输出。以下备份SHA在报告时重新核对通过：

|文件|SHA256|
|---|---|
|df_before.txt|`61ff77d85491731183a4df076e380338851bf3604f1b74c6fe6e1ce0a6d0a75d`|
|disk_bytes.txt|`9648d9f3a4396e4dea83d0f51c9478fa3f357c84851e5151b91ee9d7c486868f`|
|gpt-before.bin|`3bbdbeb4a2953d76073583428b35e452daaf52c119732b960d8d2b8086141d84`|
|gpt_backup.txt|`3e0758989efb23dd97c911bcaac0be48f6abc38a578471c77552c5cde93fa4d2`|
|gpt_verify_before.txt|`3ed97011a08407339c1314295f448d813158ae7b181220da0f2c786538c79bd5`|
|lsblk_before.txt|`d6cdfdfb38c6301e5e40c6d1d5597583338ac2bbeacb2a1316d52e8e3d3e69f1`|
|parted_free_before.txt|`efaa061d7e1fb294191776a37ae7b3afbdbbd4b114ec9a71d07189dd360938d8`|
|partition_json_before.txt|`c83db5ebe66cda58219e434639dcbe16de5b1515b50a901dd2b18f24292b0c70`|
|root_before.txt|`f79faeadff048bc8f37c6e0ab442c0be1f11217d8c02fc2772b55195ee51235f`|
|sector_bytes.txt|`240269e94afb4bbc4c643851e366bf4f0d870ff0753d250b854f748cf3516285`|
|sfdisk-before.txt|`098757dc8e740c215d1cf4d52cf35d7de72012ad125f340d3750a518c1549777`|
|swap_before.txt|`1fdaeb2146f4ab32519fba1cde294d883e65100a1e4398c87b95d112a8bcbe49`|

原始实验文件未删除或主动改写。历史Krita封存run的37份成员再次匹配原SHA；不是声称对整盘每个媒体文件进行了字节扫描。数据验证记录 `/home/mxt/TeamOOM/results/diagnostics/system_memory_watch/20261127T095026Z/protected_raw_verification.json`。本次验收原始输出独立留在repo外；代码位于mxt，没有使用新增空间创建Swap或压力负载。
