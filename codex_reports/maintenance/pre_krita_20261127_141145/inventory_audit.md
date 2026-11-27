# 清理前后盘点与完整性核验摘要

本文将本机审计记录整理为Markdown。这里只交付盘点路径、归属依据、统计及摘要核验结论，不提交JSON原件、实验采样、日志、素材、业务输出、软件或ZIP。实验状态仍为Krita INCOMPLETE、Table NEEDS_RECOLLECTION。文件数不包含目录；逻辑字节不是文件系统实际释放空间。

## 删除前盘点：主清单164条

每条路径在删除前记录文件数/逻辑字节/分配字节、目录元数据指纹和归属证据；逐项检查未变化后才删除。DBeaver/Hop归属由第三轮参数清单、下载元数据、per-round environment、GUI trace、专属workspace/流水线/输出路径确认；桌面私有存储和临时文件由应用名称、内容及实验日期确认。没有向保护目录删除或写入。

|应用|显式路径|文件数|逻辑字节|
|---|---|---:|---:|
|dbeaver|`/home/mxt/TeamOOM/runtime/apps/app_candidates/dbeaver`|1080|214869678|
|dbeaver|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/dbeaver`|13|12923930|
|hop|`/home/mxt/TeamOOM/runtime/apps/app_candidates/hop`|1558|467740250|
|hop|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/hop`|33|148794609|
|qgis|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_224114_qgis_aggregate/qgis`|12|12490626|
|dbeaver|`/home/mxt/TeamOOM/runtime/downloads/app_candidates/duckdb_jdbc-1.4.2.0.jar`|1|80926983|
|hop|`/home/mxt/TeamOOM/runtime/downloads/app_candidates/hop2.sha512`|1|159|
|hop|`/home/mxt/TeamOOM/runtime/downloads/app_candidates/apache-hop-client-2.20.0.zip`|1|391978109|
|dbeaver|`/home/mxt/TeamOOM/runtime/downloads/app_candidates/duckdb_jdbc-1.4.2.0.jar.sha256`|1|64|
|dbeaver|`/home/mxt/TeamOOM/runtime/downloads/app_candidates/dbeaver-ce-25.3.5-linux-x86_64.tar.gz`|1|124602890|
|dbeaver|`/home/mxt/TeamOOM/runtime/downloads/app_candidates/dbeaver25_release.json`|1|26357|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_exit2.png`|1|283943|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_tmp`|0|0|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_click.png`|1|216013|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_config`|1|20541|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_exit3.png`|1|244924|
|dbeaver|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/duckdb_driver.json`|1|327|
|dbeaver|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/dbeaver_Q1.sql`|1|873|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_audit_resumed`|51|6486|
|dbeaver|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/dbeaver_settings.sql`|1|463|
|dbeaver|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/duckdb_tmp`|0|0|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_project_corrected`|3|15343|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_project`|3|15318|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_config_resumed`|1|20435|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_corrected_loading.png`|1|3485390|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_install.json`|1|575|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/finalize_resumed_report.py`|1|13420|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_exit.png`|1|283943|
|dbeaver|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/dbeaver_workspace`|31|249343|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_corrected_exit_confirmation.png`|1|260354|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_project_resumed`|3|15324|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_before_resume.png`|1|284175|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_audit_corrected`|51|6494|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_download.log`|1|9483|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_audit`|52|6929|
|dbeaver|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/weather.duckdb`|1|12288|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/hop_config_corrected`|1|20437|
|dbeaver|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/dbeaver_install.json`|1|478|
|hop|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/resume_gui.py`|1|1136|
|dbeaver|`/home/mxt/TeamOOM/runtime/config/app_candidates/round3/drivers`|0|0|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/outputs/hop_Q1_resumed.csv`|1|221757814|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/outputs/hop_Q1_converted.csv`|1|221757814|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/outputs/hop_Q1_corrected.csv`|1|221835714|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/outputs/dbeaver_Q1.parquet`|1|11671664|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reports/dbeaver_Q1_verification.log`|1|480|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reports/dbeaver_Q1_verification.json`|1|4139|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reports/hop_Q1_verification.log`|1|481|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reports/hop_Q1_verification.json`|1|4156|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reports/hop_round02_failed_verification.log`|1|420|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reports/capture_evidence/dbeaver`|5|14081|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reports/capture_evidence/hop`|4|6580|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_resumed_ready.png`|1|3485663|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/dbeaver_Q1_native_success.png`|1|1812216|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_resumed_background_verified.png`|1|315426|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/dbeaver_actual_settings.png`|1|1766421|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/duckdb_driver.json`|1|327|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/dbeaver_Q1.sql`|1|873|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/dbeaver_data_sources.json`|1|934|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_resumed_native_success.png`|1|306209|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_resumed_loaded.png`|1|220895|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/dbeaver_settings.sql`|1|463|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_project_corrected`|3|15343|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_corrected_success_metrics.png`|1|246747|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/configure_duckdb.py`|1|1863|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_corrected_background.png`|1|243894|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_resumed_background.png`|1|261004|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/configure_hop.py`|1|8500|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_resumed_run_options.png`|1|220863|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_corrected_run_options.png`|1|204471|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_install.json`|1|575|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_native_run_options.png`|1|237341|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/watch_duckdb_profile.py`|1|1483|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_Q1_background.png`|1|245612|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/dbeaver_Q1_background.png`|1|1805845|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/dbeaver_fixed_driver.xml`|1|2750|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_config_corrected`|1|20437|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/hop_resumed_background_actual.png`|1|260141|
|dbeaver|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/dbeaver_install.json`|1|478|
|hop|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/reproduction/resume_gui.py`|1|1136|
|knime|`/home/mxt/.local/share/KNIME`|4|12334|
|dbeaver|`/home/mxt/.local/share/DBeaverData`|2|114|
|qgis|`/home/mxt/.local/share/QGIS`|5|941341|
|kdenlive|`/home/mxt/.local/share/kdenlive`|2|40126|
|kdenlive|`/home/mxt/.local/share/stalefiles/kdenlive`|2|38310|
|qgis|`/home/mxt/.cache/QGIS`|0|0|
|qgis|`/home/mxt/.cache/qgis_process.bin`|0|0|
|qgis|`/home/mxt/.config/Unknown Organization/qgis_process.bin.conf`|1|39|
|dbeaver|`/tmp/round3_dbeaver_sqleditor.png`|1|1667798|
|knime|`/tmp/knime_progress07_crop.png`|1|313531|
|hop|`/tmp/hop_Calculator.xml`|1|1002|
|dbeaver|`/tmp/round3_dbeaver_close.png`|1|1818296|
|hop|`/tmp/hop_SelectValues.xml`|1|2112|
|dbeaver|`/tmp/round3_dbeaver_delete.png`|1|1712336|
|dbeaver|`/tmp/round3_dbeaver_copy_ready.png`|1|1797001|
|qgis|`/tmp/QGIS3-iIxsgO`|0|0|
|knime|`/tmp/knime_context_crop.png`|1|59412|
|dbeaver|`/tmp/round3_dbeaver_complete.png`|1|1812216|
|knime|`/tmp/knime_explorer_menu.png`|1|36477|
|dbeaver|`/tmp/round3_dbeaver_start.png`|1|3409130|
|dbeaver|`/tmp/round3_dbeaver_hidden_prompt.png`|1|1729271|
|hop|`/tmp/hop_FilterRows.xml`|1|908|
|hop|`/tmp/hop_CSVInput.xml`|1|2026|
|hop|`/tmp/hop_TextFileOutput.xml`|1|1403|
|knime|`/tmp/knime_nodes_progress.png`|1|56472|
|hop|`/tmp/hop_Formula.xml`|1|1206|
|qgis|`/tmp/QGIS3-GJSYSf`|0|0|
|dbeaver|`/tmp/round3_dbeaver_paste_error.png`|1|1828067|
|qgis|`/tmp/qgis-python-crash-info-126342`|1|0|
|dbeaver|`/tmp/round3_dbeaver_libraries.png`|1|1705001|
|qgis|`/tmp/QGIS3-OYBYJl`|0|0|
|dbeaver|`/tmp/round3_dbeaver_finish_alt.png`|1|1711258|
|knime|`/tmp/knime_keyboard_context.png`|1|131992|
|dbeaver|`/tmp/round3_dbeaver_connected.png`|1|1711586|
|qgis|`/tmp/QGIS3-IoKQLF`|0|0|
|knime|`/tmp/knime_columnar_crop.png`|1|39722|
|qgis|`/tmp/QGIS3-QWTOUh`|1|414|
|dbeaver|`/tmp/round3_dbeaver_database.png`|1|1711567|
|knime|`/tmp/knime_q1_progress01.png`|1|40428|
|qgis|`/tmp/QGIS3-VRJbnL`|1|86016|
|qgis|`/tmp/QGIS3-QFdneK`|0|0|
|qgis|`/tmp/QGIS3.IFDKrX`|1|0|
|dbeaver|`/tmp/round3_dbeaver_driver.png`|1|1725207|
|dbeaver|`/tmp/round3_dbeaver_donewizard.png`|1|1663781|
|hop|`/tmp/hop_SwitchCase.xml`|1|1049|
|knime|`/tmp/knime_q1_progress02.png`|1|40122|
|dbeaver|`/tmp/round3_dbeaver_settings_applied.png`|1|1819363|
|qgis|`/tmp/QGIS3-SfWvUX`|1|86016|
|hop|`/tmp/round3_hop_run_dialog.png`|1|241199|
|qgis|`/tmp/qgis-python-crash-info-140275`|1|0|
|qgis|`/tmp/QGIS3-AGnpKC`|0|0|
|knime|`/tmp/knime_progress06_crop.png`|1|56208|
|qgis|`/tmp/QGIS3-UBEoLg`|0|0|
|dbeaver|`/tmp/round3_dbeaver_settings_result.png`|1|1766421|
|hop|`/tmp/hop_SortRows.xml`|1|1676|
|qgis|`/tmp/QGIS3-YdapsI`|1|86016|
|hop|`/tmp/round3_hop_check.png`|1|258229|
|dbeaver|`/tmp/round3_dbeaver_editor.png`|1|1795977|
|dbeaver|`/tmp/round3_dbeaver_new.png`|1|1753945|
|qgis|`/tmp/QGIS3.wENomC`|1|0|
|dbeaver|`/tmp/round3_dbeaver_realsettings.png`|1|1709298|
|dbeaver|`/tmp/round3_dbeaver_test.png`|1|1711258|
|qgis|`/tmp/QGIS3-TkWAJb`|0|0|
|knime|`/tmp/knime_execute_tooltip.png`|1|20051|
|qgis|`/tmp/QGIS3-yzluqy`|0|0|
|hop|`/tmp/round3_hop_start.png`|1|221823|
|dbeaver|`/tmp/round3_dbeaver_ready.png`|1|1684127|
|dbeaver|`/tmp/round3_dbeaver_connection.png`|1|1702898|
|qgis|`/tmp/qgis-python-crash-info-127507`|1|0|
|dbeaver|`/tmp/round3_dbeaver_library_set.png`|1|1704998|
|dbeaver|`/tmp/round3_dbeaver_fixedjar.png`|1|1704085|
|qgis|`/tmp/QGIS3.HFdpSB`|1|0|
|hop|`/tmp/hop_generate_notes.txt`|1|396|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/analysis/hop_full_lifecycle.png`|1|117679|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/analysis/dbeaver_full_lifecycle.png`|1|107450|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/analysis/table_candidates_comparison.png`|1|196991|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/analysis/table_candidate_comparison.png`|1|127344|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/analysis/all_apps_common_scale.png`|1|124898|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/analysis/all_apps_normalized_components.png`|1|231497|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/analysis/all_apps_anon_file.png`|1|170647|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/analysis/all_apps_normalized.png`|1|162711|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/analysis/raster_candidate_comparison.png`|1|129607|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/analysis/array_candidate_comparison.png`|1|130023|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/TeamOOM_round3_20261126_170421_gui_round3_reports.zip`|1|13189930|
|mixed_retired|`/home/mxt/TeamOOM/results/app_candidates/TeamOOM_round3_20261126_170421_gui_round3_reports.zip.sha256`|1|120|

## 补充临时清单10条

以下同样先盘点再删除。另有一份既有特权QGIS系统清理JSON作为简短审计保留。

|应用|路径|文件数|逻辑字节|
|---|---|---:|---:|
|qgis|`/tmp/teamoom_qgis_cleanup.py`|1|3312|
|blender|`/tmp/blender_qiKqm4`|0|0|
|hugin|`/tmp/hugin_dbgrpt-61105-20261125T202134`|1|49280|
|qgis|`/tmp/teamoom_qgis_report.py`|1|8838|
|blender|`/tmp/blender_YI8YvP`|0|0|
|blender|`/tmp/blender_tkxByP`|0|0|
|qgis|`/tmp/qgis_algorithm_dialog.py`|1|19801|
|blender|`/tmp/blender_xgG6ES`|0|0|
|qgis|`/tmp/teamoom_qgis_remove.log`|1|6546|
|qgis|`/tmp/teamoom_qgis_cleanup_state.json`|1|6924|

## APT专属安装包缓存3条

已检查DPKG包头，应用本体已卸载；只删除对应下载缓存，不操作共享依赖。

|路径|字节|删除前SHA256|
|---|---:|---|
|`/var/cache/apt/archives/kdenlive_4%3a21.12.3-0ubuntu1_amd64.deb`|2702112|`2acec7955da401689db7aeb6bb84ad2fc5d03059c4b1b86ec40a1e1ad0085912`|
|`/var/cache/apt/archives/kdenlive-data_4%3a21.12.3-0ubuntu1_all.deb`|10521156|`0ed67ee9d5455c527633a83bf13572cbace5fbc0aeecc81b98688bad69a0e336`|
|`/var/cache/apt/archives/darktable_3.8.1-2_amd64.deb`|6289234|`523113dfa5b363ccc1265a84b541f79c53af7cc79a040a165944b778d532fd06`|

## 清理后保护核验

18组保护根的91421个可读条目路径、类型、大小、mtime、ctime和符号链接目标与清理前一致。OOM特权服务子目录存在不可读范围，原报告明确列出，未更改权限或写入，未声称已遍历其内容。

|保护根|可读条目|前后相同|
|---|---:|---|
|`/home/mxt/OOM`|19547|是|
|`/home/mxt/page_hotness_research`|59803|是|
|`/home/mxt/TeamOOM/assets/baseline_assets`|8|是|
|`/home/mxt/TeamOOM/data_collection/real_cases`|0|是|
|`/home/mxt/TeamOOM/results/real_cases`|0|是|
|`/home/mxt/TeamOOM/runtime/venv`|11305|是|
|`/home/mxt/TeamOOM/runtime/apps/app_candidates/peazip_portable-11.4.0.LINUX.GTK2.x86_64`|558|是|
|`/home/mxt/TeamOOM/runtime/config/app_candidates/round2`|40|是|
|`/home/mxt/TeamOOM/runtime/config/app_candidates/handbrake`|8|是|
|`/home/mxt/TeamOOM/runtime/config/app_candidates/peazip`|0|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets`|31|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261125_171530_preflight_blocked/peazip`|1|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261125_171530_preflight_blocked/handbrake`|1|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261125_194918_gui/peazip`|20|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261125_194918_gui/handbrake`|16|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip`|14|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/peazip`|28|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake`|41|是|

42项关键文件前后SHA256均相同，包含16个PeaZip输入、22份有效原始记录、2个保留业务输出、旧Krita ORA及Table十轮归档。下面只列文件摘要，不包含原文件内容。

|路径|核验SHA256|前后相同|
|---|---|---|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/videos/bbb_sunflower_1080p_30fps_normal.mp4`|`ae51005850b0ff757fe60c3dd7a12d754d3cd2397d87d939b55235e457f97658`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/DJI-Mavic-3-Pro.DNG`|`f33ddaf2a7fa70b395abced251faccea11100d2ab7e54ae0a6adbff043d72027`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Apple-iPhone-12-Pro.DNG`|`e91e77a4533ed7cce551d83330676ea5c47dd5e55fb38adda7819366afdbdfc2`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Sony-a7III.ARW`|`250784580ea527442c09004417bb0eead484f2bf3ee8f9121a776ac65bb50d0f`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Canon-EOS-R.CR3`|`cfd118af4477ef37538eb953421572a7a5c80694e59764049223107cc0c9ae83`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Nikon-Z6.NEF`|`8ca94584578b35a422744c1a610174ce37df0691588edfdecaec3111b3fbbb02`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Canon-5D-Mark-IV.CR2`|`02b23f9cc6dc4c99fb39aa4d1f65ac227804d06461ac1bd0f842aa2f3beb8fe4`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Sony-DSC-R1.SR2`|`921c5f2513dd1671a9089e73fc778fc3573bc4cb70a3a555d0414661d0e62274`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Nikon-Coolpix-P1000.NRW`|`1d9470ee083f914e51aa0be782161b432f27f87dbef551a59ec435f5dbc289dd`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Canon-EOS-D60.CRW`|`2b98659ecff170af1dfe44f89b493139e75e995b2979686f6ff0847cfb56b97f`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/OM-System-OM-1.ORF`|`bf2eef6becc0851e48231617c3e2eac27a2cdb44c75b93035c561d837952c18b`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Panasonic-G9.RW2`|`cfb015a89d7af92306328868e6d87ac7974c427612608016821dfb336e8e3faa`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/manifests/official_SHA256SUMS.txt`|`9f0ba538a223c1a9bfb2022ddeab489f152251006c94df72d951f0c15d4ce8e8`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Sony-DSC-F828.SRF`|`07739f94bcab0c7e198d418ac65172d0dce04bb84a7683ecffd0bfe4b32f6d79`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Fujifilm-X-T4.RAF`|`871836938ffa695f4c41765ddb107c2703ce755f7f3ced7e10f9e04746f1734e`|是|
|`/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/raw_photos/Ricoh-GR-III.DNG`|`05513ee72f7cac4165534c9f64995412084f414a033c80c473c79fd94154292e`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01/gui_actions.jsonl`|`11ba68e977be8308d209beda6c3b390281463c84ebb4fdadc562dc26caba73f9`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01/worker_watcher.log`|`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01/phase_trace.jsonl`|`5c4c4c08e528fecc9f11797040f41c187e80ae3164e8ce99864da8a58a844a7a`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01/task_memory.csv`|`1701551cc66c42cfabf560b4d6b095a640f43893a2c81b3ee5992d5fa512c153`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01/backend_argv.json`|`0ad51350d0c1f85409ab3bfb69afd57150f4a2d03e2cfeb22a939efc54e24e71`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01/capture_summary.json`|`6b9e5b186ca2b17bc00b2ce3062bec178c05db723725d520bcaae5ba1e133c37`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01/process_tree.csv`|`91031c4f4d63b1d1f074c07ab8b9247d6a7c826420fcbee3b5eb9a5e0d2fd597`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01/ancestor_limits.json`|`c9efffeb74ac4237413e0d85a4c8bc7eb665ed98021c51149bd40a2032e9b8e6`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01/environment.json`|`091898d489b60336c018757e309c8363bc842420ec440e1a2108a9f15978869c`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01/application.log`|`951a6bccb36eddaea1c65c2610a3250eda0b4e49c089b9e92a5aaf34b5c8c40b`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/completion_watcher.log`|`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/gui_actions.jsonl`|`90cbcfe43be500b9cd2bdc36e2c98f90a65804a6d37dae672e6f65862b7d7027`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/native_activity.log`|`0064518c089d670789904cc57d4c89dd530ff1cc743b023fa17964708ba60ff7`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/phase_trace.jsonl`|`7e680acb217ca290014d46db9c3c26954c24d82dbcf6b66da34ff79591dbee82`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/timing_override.json`|`c04b75ab87c5bdf5c4dd92c71acb6218adc468a1c26731e9c2bdaff478f4e658`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/task_memory.csv`|`392f43166e91687651de9a2cec9df12d692dc53cb8141a691df3401203391bc6`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/capture_summary.json`|`f55ef165191cf8e28b501abae2de58eab9ce5fb69ae1ab88a702acc9b1d711ec`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/native_log_path.txt`|`f414473c7a349955bede7c0eefcdd2083a2fdd3fbbabb6e0d740cf459f39a84d`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/process_tree.csv`|`1f6f9a9867ceae9417889e7169d1ffd78627032771fbd3ca5da70a5acb7046e4`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/ancestor_limits.json`|`ad9f80cff0610702ab68d1f51c513c37d3ea11f8048ac19b2b599b1ae8965821`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/environment.json`|`c8dd182dbd8da0d2c899898073c8ed1c87f3aab8820bc316ff0f9360fbadd52b`|是|
|`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02/application.log`|`5508c5126d5fbeae79e9a2760a7d338ee6fc22ebb84c67cb8e9a9570213bbcb1`|是|
|`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3/outputs/peazip_medium_128m.7z`|`2e3d17decefee564ccbce0080d40d256806986c33b81bd0584967a5b011a96c1`|是|
|`/home/mxt/TeamOOM/results/app_candidates/20261126_142729_gui_round2/outputs/bbb_0-20_x265_medium_rf22.mkv`|`d4a7cdbd1329452ad8df2bb3c8c6c619219255651c12a4ce4d6794a47d615664`|是|
|`/home/mxt/OOM/assets/krita_8000_manual/blank_8000x8000.ora`|`1d310235030f6feaf02a84aa4636e419e19c7b653724d776908965eaaebe3054`|是|
|`/home/mxt/OOM/data_collection/shared_recovery_20261120/OOM_Dataset_20261101/Table/OOM_Table_10rounds_20261101.tar.gz`|`fd63e5961321bbaf1ebe0bc1e62102f1772beae0f8020a0ac0de6a952216a3b8`|是|

## 交付文件验证

解析20份本机审计JSON；18组目录与42项关键摘要通过；保留版第三轮52项SHA256条目核验通过；保留报告ZIP18个成员通过完整性检查，ZIP SHA256为 `3ba6696d9b55e975c5bfb54cd3befa0f8bce8573f700facb8abbef373012f8e0`。ZIP仍留在本机，本次只上传Markdown。

三次删除窗口可用空间增量之和：2240110592字节（2.086266GiB）。新有效保留汇总使用PeaZip第三轮与HandBrake第二轮固定20秒，无重新运行业务应用。旧混合PNG已删除后由仅含这两者的图替换，故部分原路径有新内容；其替代文件与新保留汇总逐一摘要相同，不属于淘汰数据复原。专属淘汰路径均移除。

完整本机审计目录：`/home/mxt/TeamOOM/results/maintenance/pre_krita_cleanup_20261127_141145`。当前实际仓库mxt保持 `81f1f27d82b861b05f8a479a170035d39225fd67`，源码与工作区未改变；此次新报告提交只发生在独立mxt_codex检出。
