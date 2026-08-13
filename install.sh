#!/usr/bin/env bash
# 安装并启动 lenovo-fn-osd（KDE Plasma 下的联想 Fn 键 OSD 弹窗）
# 需要在图形会话（Wayland/X11 均可）里运行，因为要用 systemctl --user 和会话 DBus。
set -euo pipefail
cd "$(dirname "$0")"

install -Dm755 lenovo-fn-osd.py "$HOME/.local/bin/lenovo-fn-osd.py"
install -Dm644 lenovo-fn-osd.service "$HOME/.config/systemd/user/lenovo-fn-osd.service"

systemctl --user daemon-reload
systemctl --user enable --now lenovo-fn-osd

echo
echo "✅ 已安装并启动 lenovo-fn-osd"
echo "   状态：$(systemctl --user is-active lenovo-fn-osd)"
echo
echo "验证方法：按 Caps Lock / Num Lock / Fn+Esc / Fn+Q，应出现 KDE 风格弹窗。"
echo "查看日志：systemctl --user status lenovo-fn-osd --no-pager"
echo "卸载方法：systemctl --user disable --now lenovo-fn-osd && rm -f ~/.local/bin/lenovo-fn-osd.py ~/.config/systemd/user/lenovo-fn-osd.service && systemctl --user daemon-reload"
