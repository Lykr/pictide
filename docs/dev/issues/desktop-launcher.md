# 桌面启动与托盘退出

## 概述

沿用系统浏览器和现有服务，解决双击启动、首次准备进度和便捷退出三个问题。

状态：Windows 原生托盘与轻量桌面启动已实现，源码入口和真实便携程序验证通过；四平台构建与启动冒烟全部通过，尚未发布新版本。

## 架构

```mermaid
flowchart TD
    User[双击桌面入口] --> Entry[轻量启动入口]
    Entry --> Host[现有 Host 与启动准备]
    Host --> Progress[临时启动终端：初始化进度]
    Host --> Service[既有 HTTP 服务与应用生命周期]
    Service --> Browser[系统浏览器：Pictide Web]
    Service --> Tray[原生系统托盘：状态与退出]
    Tray --> Open[重新打开网页 / 打开日志]
    Tray --> Stop[请求正常停止服务]
    CLI[显式命令行模式与 CI] --> Host
```

## 职责边界

| 组成 | 变更 |
| --- | --- |
| 桌面入口 | 保留双击启动方式；首次依赖准备、词库初始化与模型下载使用启动终端显示进度。就绪后自动打开浏览器，收起由启动器创建的临时终端；失败时保留错误输出。 |
| Host | 复用现有模型准备、HTTP 就绪后打开浏览器及生命周期；桌面模式增加就绪通知与正常停止信号，命令行模式继续支持 Ctrl+C。 |
| 托盘 | Windows 优先用标准库 `ctypes` 调用系统 API；提示显示服务状态，菜单提供“打开 Pictide / 打开日志目录 / 退出 Pictide”。托盘动作交给现有服务事件循环处理。 |
| 模型与日志 | 沿用现有下载进度、校验、续传和 `data/logs/`，不增加图形进度回调、独立日志面板或启动器配置文件。 |
| 发行与 CI | 继续共用现有 Python 及后端运行时，不增加 GUI 运行时；显式 CLI 与无桌面环境保留终端，不初始化托盘。现有四平台构建与冒烟调用保持可用。 |

程序入口和托盘统一复用网站的 Pictide 图标：沿用 `web/public/icons/pictide.svg` 的设计，以已有 `pictide-512.png` 为平台图标导出源。构建时生成 Windows `.ico` 等平台格式，复用已有 Pillow；不增加图标专用运行时依赖，也不维护另一套图案。

启动提示、初始化进度、服务状态、托盘菜单和错误摘要支持简体中文与英文，启动时按系统首选显示语言选择：`zh-CN`、`zh-SG`、`zh-Hans` 等简体中文语言使用中文，英语及其他未支持语言使用英文；识别失败也回退英文。使用轻量双语文案表，不增加第三方依赖或语言选择界面。底层库原始日志保留原文；网页继续使用现有语言设置。

## 调用和数据流

```mermaid
sequenceDiagram
    actor User as 用户
    participant Entry as 桌面启动入口
    participant Host as 服务与启动准备
    participant Tray as 系统托盘
    participant Browser as 系统浏览器与文件管理器
    User->>Entry: 双击启动
    Entry->>Host: 当前端口、数据目录与访问范围
    Host-->>Entry: 首次准备进度 / 失败信息
    Host->>Host: 模型完成校验后启动 HTTP 服务
    Host-->>Entry: 服务就绪
    Host->>Tray: 加入托盘，显示运行状态
    Host->>Browser: 打开 Web 界面
    Entry->>Entry: 收起自己的临时启动终端
    User->>Tray: 打开 Pictide / 打开日志目录
    Tray->>Browser: 通过系统打开网页或日志目录
    User->>Tray: 退出 Pictide
    Tray->>Host: 请求正常停止
    Host->>Host: 沿现有生命周期收尾
    Host->>Tray: 移除图标并退出
```

## 交互范围

- **双击就能开始**：服务就绪后自动打开现有网页；关闭网页后，可通过托盘再次打开。
- **首次等待看得见**：复用启动窗口里的模型下载百分比、校验及失败信息。模型全部准备完成后才允许进入应用，下载失败保留有效部分供下次续传。
- **需要时容易退出**：服务运行期间保留托盘，明确提供退出操作；退出执行正常清理，避免只关闭网页后找不到后台服务。

已取消独立控制窗、Tkinter/ttk、独立图形进度窗、地址管理面板与开机自启；后续按实际使用需要单独评估。首次进度采用已有终端输出，本期不以另一套界面替换它。

## 重点关注

- 先完成 Windows 原生托盘与桌面入口验证；macOS/Linux 后续分别评估原生集成，既有 CLI 保持可用。不为统一桌面外观引入额外运行时。
- 只收起启动器自己创建的终端；用户主动打开的命令行终端保留。托盘不可用时保留终端退出入口。
- 同一数据目录重复桌面启动时，重新打开已有实例网页，避免新增第二份后台服务；其他实例和数据目录继续独立。
- 端口、数据目录与局域网参数沿用原入口，运行地址在启动输出和日志中可查，不增加第二处设置。
- 包体积与常驻资源消耗以相同源码、相同模型准备方式的 CLI 包为基线实测；此前 Tcl/Tk 的约 3.8 MiB 压缩估算不再纳入方案。
- 少数冒烟覆盖首次下载、已有模型启动、失败可见、关闭网页后重开、托盘退出和 CLI；验证使用独立数据目录及端口，保留主实例和用户任务。原生桌面交互与 headless CI 结果分别记录。
- 文案验证覆盖简体中文、英文、未支持语言与语言检测失败的英文回退。

## 实现与验证

- `backend/desktop.py` 负责桌面会话、数据目录单实例锁、启动地址与生命周期；`backend/windows_tray.py` 提供标准库原生托盘和自有控制台处理，`backend/desktop_text.py` 提供双语文案。
- Windows 源码入口默认以 `--desktop` 启动独立进程，`-Cli` 保留用户终端；便携入口对应 `--desktop` 与首参数 `--cli`。`--no-browser` 关闭托盘和自动浏览器，Linux/macOS 保持现有入口。
- 首次准备前先绑定端口，HTTP 在模型准备成功后才监听；同数据目录锁被占用时检查原实例的 bootstrap 与数据目录，再打开原地址。端口占用提前失败，启动窗口保留错误信息并等待 Enter。
- 临时实例只使用独立数据和端口，未提交生图任务。真实 Windows 进程已验证托盘注册、页面重开、日志入口、正常退出、锁释放和重复启动复用；`--lan` 的本机网卡地址可访问且写入日志。自建控制台实测从可见变为隐藏，退出后清理完成。
- 少数冒烟覆盖系统语言、模型下载和失败、实际 Win32 消息及浏览器就绪；初次集成发现的错误收尾文案缺失已补齐并复测。

### 2026-10-19 交付验证

功能提交 `75dd794` 的[四平台 Actions](https://github.com/Lykr/pictide/actions/runs/39263181119) 全部通过：Windows x64、Linux x64、macOS ARM64 和 Intel 均完成原生打包、首次模型下载与隔离启动冒烟；手动运行的 `publish` 按预期跳过。Windows 便携 ZIP 另做本机真实桌面验证，CLI 的 Ctrl+C 与托盘正常退出均返回 0。源码 `start.ps1` 使用包含中文、空格的独立数据路径验证了参数传递及启动窗口自动收起。

| 本机 Windows 测量 | 结果 |
| --- | --- |
| 新 ZIP | 69,160,630 字节，约 65.96 MiB |
| 相比前一次相同前端与依赖的 CLI 包 | 增加 12,710 字节，约 12.4 KiB |
| 新图标 | 21,091 字节，沿用网站图标 |
| 额外 GUI 运行时 | 无；构建检查未发现 Tcl/Tk、Qt 或 wx |
| 同包 warm idle 进程树工作集差值 | 桌面模式约增加 1.90 MiB |
| 同包 warm idle 进程树私有提交差值 | 桌面模式约增加 0.47 MiB |

内存是同一台机器一次空闲采样，包含各自控制台进程，不能视为跨平台固定开销。桌面验证中的浏览器请求由无界面 stub 记录，确认 HTTP 就绪后才调用系统浏览器接口；未执行真实生图或 GPU 任务。验证报告保存在开发目录 `dev/verification/desktop-launcher-20261019/`，产物位于 `releases/desktop-tray-20261019-windows-final/`，均不提交。

## 技术依据

### Windows 高 DPI 与启动终端修复

原实现只调用 `ShowWindow(GetConsoleWindow(), SW_HIDE)`；Windows Terminal/ConPTY 中该句柄并非实际终端窗口，进程继续运行时可能留下终端标签页。现将桌面启动分成临时进度进程和 `CREATE_NO_WINDOW` 服务进程；托盘注册成功后进度进程退出，失败保留提示，托盘不可用时服务先正常退出，再由原进度进程回退到终端运行。CLI 与无浏览器模式沿用原入口。

托盘专用线程在创建窗口前启用 Per-Monitor V2，根据任务栏 DPI 请求图标尺寸，弹出菜单前让隐藏所有者窗口跟随菜单所在显示器。所有设置仅在 Pictide 自己的线程与进程中生效，未修改注册表、系统缩放或默认终端。

本机实际 192 DPI（200%）环境下，源码与新便携 EXE 均验证了启动进程返回 0、服务控制台窗口句柄为 0、托盘窗口 PMv2、重复启动复用、正常退出与端口占用失败；ZIP 的原 CLI/资源/词库冒烟通过。报告位于 `dev/verification/windows-tray-fixes-20261019/`。未触发 GitHub Actions；4K 菜单的最终视觉效果需在新程序运行后观察。

[GetConsoleWindow](https://learn.microsoft.com/en-us/windows/console/getconsolewindow) 与 [SetThreadDpiAwarenessContext](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setthreaddpiawarenesscontext) 为相关系统 API 依据。

[Windows 通知区域](https://learn.microsoft.com/en-us/windows/win32/shell/notification-area)提供原生托盘能力；Python 侧只做薄适配，业务界面仍由现有浏览器承担。
