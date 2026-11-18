#!/usr/bin/env python3
"""坐标采集工具：输入标签后倒计时3秒，把鼠标移到目标位置，时间到自动记录。
用法: python3 pick_coords.py
分辨率变化时需要重新采集坐标。
"""
import subprocess
import time


def get_mouse_pos():
    out = subprocess.run("xdotool getmouselocation --shell", shell=True, capture_output=True, text=True).stdout
    x = y = None
    for line in out.splitlines():
        if line.startswith("X="):
            x = int(line.split("=")[1])
        if line.startswith("Y="):
            y = int(line.split("=")[1])
    return x, y


def main():
    print("=" * 50)
    print("坐标采集工具（倒计时模式）")
    print("1. 输入标签名，按回车开始倒计时3秒")
    print("2. 在3秒内把鼠标移到目标位置，不要动")
    print("3. 时间到自动记录坐标")
    print("输入 q 退出")
    print("=" * 50)

    while True:
        label = input("\n请输入这个位置的名称标签（或q退出）: ").strip()
        if label.lower() == "q":
            break
        if not label:
            continue
        
        print(f"  3秒内把鼠标移到 [{label}] 的位置...")
        for i in range(3, 0, -1):
            print(f"  {i}...", end="\r")
            time.sleep(1)
        
        x, y = get_mouse_pos()
        print(f"  ✓ '{label}': ({x}, {y}),")


if __name__ == "__main__":
    main()
