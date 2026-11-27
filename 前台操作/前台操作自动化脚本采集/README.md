# Krita 低压 → 高压 → 中压自动化

在已登录并解锁的 Ubuntu GNOME 桌面终端执行。从前台目录的 [素材说明](../素材/README.md) 部署 ORA，把 `gui` 改为本目录的绝对路径。生成配置时使用 [低高中文档模板](configs/collection.rapid-9000-medium-tail-extended.json)，`assets-root` 使用绝对 ASCII 路径。运行前关闭已有的 Krita 窗口。

```bash
gui="/path/to/前台操作/前台操作自动化脚本采集"
sudo apt-get install git python3-venv krita python3-pyatspi at-spi2-core xdotool wmctrl x11-utils
python3 -m venv "$HOME/oom_lab/krita-venv"
fgpy="$HOME/oom_lab/krita-venv/bin/python"
"$fgpy" -m pip install Pillow==11.1.0

read -r width height < <(xdotool getdisplaygeometry)
settings="$HOME/oom_lab/config/krita-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$HOME/oom_lab/config"
"$fgpy" "$gui/scripts/prepare_handoff_config.py" --assets-root "$HOME/OOM_assets" \
  --display-size "$width" "$height" --output "$settings"
```

只执行 Krita 自动化时，传入低压 ORA、三阶段配置和素材清单。脚本输出阶段事件，用于确认 GUI 操作进度。

```bash
"$fgpy" "$gui/scripts/krita_auto.py" "$HOME/OOM_assets/krita_rapid_9000_46/light_9000.ora" \
  --settings "$settings/foreground_config.json" --assets-manifest "$settings/foreground_assets.json"
```

要生成可用于四任务实验的独立参考曲线，从包含已提交前台源码的 Git 检出运行采集器，并把结果保存到仓库外。采集器先检查图形会话、素材、内核日志权限、内存与 Swap 条件，再通过 cgroup 采样。命令输出中的 `run` 是该轮目录，验收状态为 `PILOT_VALID` 时可供后续运行按要求使用。

```bash
"$fgpy" "$gui/scripts/collect_krita.py" collect \
  --config "$settings/foreground_config.json" --operation krita --rounds 1 \
  --results "$HOME/oom_lab/results/krita"
```

[四任务复现](../../复现实验.md) · [场景时序和验收](TIMED_CAPTURE.md)
