# 懒得连校园网 · iOS 风格界面

用 iOS 的设计语言重做的界面层：干净的留白、圆角卡片、毛玻璃、柔和色彩，
状态卡是整页唯一的「主角」，连接状态、自动连接入口、操作反馈三处重新排过。

界面本身是**单文件纯前端**（`index.html`，HTML + CSS + JS 全内联，零依赖），
`app.py` 只是把它装进一个无地址栏的桌面窗口 + 托盘，不改动页面逻辑。

## 直接看

双击 `index.html` 即可，任何现代浏览器都能跑。

## 跑成桌面程序

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed \
    --name CampusNetIOS --icon app.ico \
    --add-data "index.html;." --add-data "app.ico;." \
    app.py
```

产物在 `dist/CampusNetIOS.exe`，改成想要的名字即可。

启动器做的事：
- 用系统 Edge / Chrome 的 `--app` 模式开窗口（无地址栏无标签页，体积只有几百 KB，
  不必背上 Electron 运行时）
- 固定 420×860 手机竖屏尺寸、屏幕居中；屏幕矮时自动收高
- 独立 `user-data-dir`，不碰日常浏览器的配置
- 托盘常驻：关窗口不退出，点图标回来，右键退出
- 单实例：重复启动只把已有窗口叫到前台

## 功能

保留原程序全部内容：连接状态（已连接 / 未连接 / 正在连接 / 认证失败 / 自动重连暂停）、
学校与 SSID、在线时长、IP、认证服务器、重连次数、断线自动重连、运行日志、
学号密码、多学校切换、开机自启、检测间隔、主题（浅色 / 深色 / 跟随系统）。

连接过程是**真实的本地状态机**：三段推进（检测网络 → 获取地址 → 提交认证）、
失败按原因分账、12/20/30 秒退避重试、连续失败转暂停、欠费/锁定不重试。

## 接真实认证

`index.html` 里的状态机收敛在 `settle()` 与 `applyResult()` 两个函数上。
接后端时，把 `eportal.py` / `portal.py` 的认证结果按
`{ok:true}` 或 `{kind:'credential'|'service'|'network'}` 传进 `settle()`，
UI 层不需要改。

## 设计文档

- [`design/visual-spec.md`](design/visual-spec.md) —— 色彩、字体层级、6 档圆角、3 级阴影、
  毛玻璃配方、断点、状态卡五态的逐像素定义
- [`design/motion-spec.md`](design/motion-spec.md) —— 13 条状态转移、9 组动效参数、
  手势、反馈三级、无障碍降级、29 条验收清单

## 许可

MIT，与原项目一致。
