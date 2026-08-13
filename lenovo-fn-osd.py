#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lenovo Fn-key OSD for KDE Plasma (works on Wayland and X11).

在 KDE Plasma 下为联想笔记本的 Fn 组合键显示原生 OSD 弹窗：

  * Fn+Q      切换电源管理方案（监听 /sys/firmware/acpi/platform_profile，
              low-power/balanced/performance 三档循环）
  * Caps Lock 大写锁定（监听 /sys/class/leds/*capslock*/brightness）
  * Num Lock  数字小键盘锁定（监听 /sys/class/leds/*numlock*/brightness）
  * Fn+Esc    Fn 锁定（监听 /sys/class/leds/*fnlock*/brightness）

触摸板开关（Fn+M/Fn+F7）与键盘背光（Fn+Space）KDE Plasma 6 已自带 OSD，
本守护进程不再重复处理。

弹窗通过 plasmashell 的 org.kde.osdService DBus 接口显示，与系统原生
弹窗（音量、亮度、触摸板、背光）风格完全一致；plasmashell 不可用时
回退到 notify-send。

无第三方依赖，仅需 Python 3 标准库 + gdbus。仅需读取 sysfs，无需 root。
"""

import glob
import os
import subprocess
import sys
import threading
import time

POLL_INTERVAL = float(os.environ.get("LENOVO_OSD_POLL", "0.25"))
SUPPRESS_SECS = float(os.environ.get("LENOVO_OSD_SUPPRESS", "1.5"))

OSD_SERVICE_DEST = "org.kde.plasmashell"
OSD_SERVICE_PATH = "/org/kde/osdService"

# platform_profile 取值到 KDE OSD 认识的名字的映射（KDE 不认识 low-power，
# 会渲染空弹窗；PPD 里它对应 power-saver）
PROFILE_ALIAS = {"low-power": "power-saver"}

# 各锁定键 LED 的 (开启图标, 开启文案, 关闭文案)
LED_OSD = {
    "capslock": ("keyboard-caps-locked", "大写锁定 已开启", "keyboard-caps-disabled", "大写锁定 已关闭"),
    "numlock":  ("input-keyboard", "数字锁定 已开启", "input-keyboard", "数字锁定 已关闭"),
    "fnlock":   ("input-keyboard", "Fn锁定 已开启", "input-keyboard", "Fn锁定 已关闭"),
}


def default_led_path(pattern):
    """返回第一个匹配的 LED brightness 路径，找不到返回 None。"""
    matches = sorted(glob.glob(pattern))
    return matches[0] if matches else None


class LenovoFnOsd:
    def __init__(self, debug=False):
        self.debug = debug
        self.states = {}            # key -> 上次读到的值
        self.last_kde_profile_switch = 0.0  # KDE 自带快捷键切换方案的时刻（用于去重）
        self.paths = self._resolve_paths()
        if self.debug:
            for k, v in self.paths.items():
                print(f"[lenovo-fn-osd] source {k}: {v}", flush=True)

    def _resolve_paths(self):
        return {
            "profile": os.environ.get("LENOVO_OSD_PROFILE", "/sys/firmware/acpi/platform_profile"),
            "capslock": os.environ.get("LENOVO_OSD_CAPS") or default_led_path("/sys/class/leds/*capslock*/brightness"),
            "numlock": os.environ.get("LENOVO_OSD_NUM") or default_led_path("/sys/class/leds/*numlock*/brightness"),
            "fnlock": os.environ.get("LENOVO_OSD_FN") or default_led_path("/sys/class/leds/*fnlock*/brightness"),
        }

    def read(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        except OSError:
            return None

    # ---------------- OSD 显示 ----------------

    def _osd_call(self, method, args):
        try:
            subprocess.run(
                ["gdbus", "call", "--session", "--dest", OSD_SERVICE_DEST,
                 "--object-path", OSD_SERVICE_PATH, "--method", method, *args],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            return True
        except Exception:
            return False

    def _notify_fallback(self, icon, text):
        try:
            subprocess.run(["notify-send", "-a", "Lenovo Fn OSD",
                            "-i", icon, text],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=3)
        except Exception:
            pass

    def show_text_osd(self, icon, text):
        if self.debug:
            print(f"[lenovo-fn-osd] OSD text: icon={icon!r} text={text!r}", flush=True)
        if not self._osd_call("org.kde.osdService.showText", [icon, text]):
            self._notify_fallback(icon, text)

    def show_profile_osd(self, profile):
        alias = PROFILE_ALIAS.get(profile, profile)
        if self.debug:
            print(f"[lenovo-fn-osd] OSD profile: {profile!r} -> {alias!r}", flush=True)
        if not self._osd_call("org.kde.osdService.powerProfileChanged", [alias]):
            icons = {"power-saver": "battery-profile-powersave",
                     "balanced": "speedometer",
                     "performance": "battery-profile-performance"}
            self._notify_fallback(icons.get(alias, "battery"), {"power-saver": "省电模式",
                                     "balanced": "平衡模式", "performance": "性能模式"}.get(alias, alias))

    # ---------------- KDE 自带快捷键去重 ----------------

    def _start_kde_shortcut_monitor(self):
        """监听 kglobalaccel：用户按 Meta+B（KDE 自带"切换电源管理方案"）
        时 PowerDevil 自己会弹 OSD，这里记下时刻以抑制我们的重复弹窗。"""

        def run():
            try:
                proc = subprocess.Popen(
                    ["gdbus", "monitor", "--session", "--dest", "org.kde.kglobalaccel",
                     "--object-path", "/component/org_kde_powerdevil"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                for line in proc.stdout:
                    if "globalShortcutPressed" in line and "'powerProfile'" in line:
                        self.last_kde_profile_switch = time.monotonic()
                        if self.debug:
                            print("[lenovo-fn-osd] KDE native profile switch detected, suppressing duplicate OSD", flush=True)
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()

    # ---------------- 主循环 ----------------

    def run(self):
        self._start_kde_shortcut_monitor()
        while True:
            now = time.monotonic()

            # 电源管理方案（Fn+Q）
            v = self.read(self.paths["profile"])
            if v is not None:
                if "profile" in self.states and self.states["profile"] != v:
                    if now - self.last_kde_profile_switch > SUPPRESS_SECS:
                        self.show_profile_osd(v)
                self.states["profile"] = v

            # 锁定键 LED（Caps / Num / FnLock）
            for key, (icon_on, text_on, icon_off, text_off) in LED_OSD.items():
                path = self.paths[key]
                if not path:
                    continue
                v = self.read(path)
                if v is None:
                    continue
                if key in self.states and self.states[key] != v:
                    on = v not in ("0", "")
                    self.show_text_osd(icon_on if on else icon_off, text_on if on else text_off)
                self.states[key] = v

            time.sleep(POLL_INTERVAL)


def main():
    debug = "--debug" in sys.argv
    LenovoFnOsd(debug=debug).run()


if __name__ == "__main__":
    main()
