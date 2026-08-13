# lenovo-fn-osd

> ⚠️ **AI 生成声明**：本程序由 AI 生成，如果你比较介意 AI 生成的内容，请谨慎使用。

在 KDE Plasma（Wayland / X11 均可）下，为联想笔记本的 Fn 组合键显示**系统原生风格**的 OSD 弹窗。

已适配并在 ThinkBook 16 G4+ IAP（Ubuntu 26.04 + Plasma 6.6.6, Wayland）上实测通过。

## 功能

| 按键 | 弹窗内容 | 实现方式 |
|---|---|---|
| Fn+Q | 电源管理方案：性能模式 / 平衡模式 / 省电模式 | 监听 `/sys/firmware/acpi/platform_profile`（`low-power` 归一化为 `power-saver`）|
| Caps Lock | 大写锁定 已开启 / 已关闭 | 监听 `/sys/class/leds/*capslock*/brightness` |
| Num Lock | 数字锁定 已开启 / 已关闭 | 监听 `/sys/class/leds/*numlock*/brightness` |
| Fn+Esc | Fn锁定 已开启 / 已关闭 | 监听 `/sys/class/leds/*fnlock*/brightness` |

> 触摸板开关（Fn+M / Fn+F7）和键盘背光（Fn+Space）KDE Plasma 6 自带 OSD，
> 本守护进程不重复处理。

## 原理

- Fn+Q / Fn+Esc / Fn+Space / Fn+M 等组合键由笔记本固件（EC）直接处理，**不会**
  产生键盘事件（本机已确认 ideapad 输入设备不报告这些按键），只体现在 sysfs 里：
  电源方案在 `platform_profile`，Fn 锁/大小写/数字锁在 LED brightness 节点。
  因此用轻量轮询（默认 0.25s，只读几个字节）检测变化。
- 弹窗调用 plasmashell 的 `org.kde.osdService` DBus 接口
  （`powerProfileChanged` / `showText`），与音量、亮度、背光等系统弹窗外观一致。
  plasmashell 不可用时回退 `notify-send`。
- 用户按 KDE 自带的"切换电源管理方案"快捷键（默认 **Meta+B**）时，PowerDevil
  自己会弹 OSD；守护进程监听 kglobalaccel，在该快捷键触发后 1.5 秒内抑制
  自己的重复弹窗。

## 安装

```bash
cd lenovo-fn-osd
./install.sh        # 复制到 ~/.local/bin，注册并启动 systemd 用户服务
```

安装后按 Caps Lock / Num Lock / Fn+Esc / Fn+Q 即可看到弹窗。

## 自测

- 电源方案：`systemctl --user status lenovo-fn-osd` 运行中时按 Fn+Q；
  或通过 PPD 切换方案也会弹窗：
  ```bash
  gdbus call --system --dest net.hadess.PowerProfiles --object-path /net/hadess/PowerProfiles \
    --method org.freedesktop.DBus.Properties.Set net.hadess.PowerProfiles ActiveProfile "<'balanced'>"
  ```
- 无 GUI 环境下验证逻辑（用临时文件模拟 LED）：
  ```bash
  printf 0 > /tmp/caps; LENOVO_OSD_CAPS=/tmp/caps python3 lenovo-fn-osd.py --debug
  # 另开终端：printf 1 > /tmp/caps   →  应打印 OSD text: icon='keyboard-caps-locked' ...
  ```

## 调试

```bash
journalctl --user -u lenovo-fn-osd -f          # 服务日志
python3 ~/.local/bin/lenovo-fn-osd.py --debug  # 前台运行调试（先停服务）
```

环境变量（调试/适配用）：`LENOVO_OSD_PROFILE`、`LENOVO_OSD_CAPS`、`LENOVO_OSD_NUM`、
`LENOVO_OSD_FN`（指定检测路径）、`LENOVO_OSD_POLL`（轮询间隔秒）、
`LENOVO_OSD_SUPPRESS`（去重窗口秒）。

## 卸载

```bash
systemctl --user disable --now lenovo-fn-osd
rm -f ~/.local/bin/lenovo-fn-osd.py ~/.config/systemd/user/lenovo-fn-osd.service
systemctl --user daemon-reload
```

## 备注

- KDE 原生"切换电源管理方案"弹窗（非 Fn+Q，仅快捷键触发）：
  系统设置 → 快捷键 → 电源管理 → **切换电源管理方案**（默认 Meta+B / Battery 键）。
- 需要的只是读取 sysfs，无需 root；对 Wayland 无特殊依赖。
