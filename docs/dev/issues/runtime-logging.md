# 运行日志整理

## 概述

统一启动、运行与异常日志，托管 ComfyUI 单独轮换，日志入口直接打开当前应用日志。

## 架构

```mermaid
flowchart LR
    Host[既有 Host / CLI / 桌面 worker] --> Log[Python logging]
    Tasks[既有任务生命周期] --> Log
    Log --> AppFile[logs/pictide.log]
    Managed[托管 ComfyUI 子进程输出] --> ComfyFile[logs/comfyui.log]
    Launcher[桌面启动入口] --> Temp[tmp 中有数量上限的启动兜底]
    Tray[托盘 / 菜单栏查看日志] --> AppFile
```

## 职责边界

- 保持 Host、应用、任务与生图服务的现有业务边界；日志工具只负责格式、轮换、异常记录和启动输出收尾。
- `backend/runtime_logging.py` 提供 `make_log_handler(path)`，统一 UTF-8、每份 1 MiB、保留 3 份备份；应用默认 INFO，通过 `PICTIDE_LOG_LEVEL=DEBUG` 启用调试。保留外部日志配置，不开启 HTTP 访问日志。
- 主进程与线程未处理异常、asyncio 与 HTTP 服务异常进入应用日志，异常保留调用栈。日志格式包含时间、级别、PID、模块；任务事件包含任务 ID、后端 ID/类型、耗时和失败信息，避免写入提示词、密钥及请求正文。
- ComfyUI 的 stdout/stderr 通过所属进程的读取线程写入独立轮换日志，结束时排空并释放文件；外部 ComfyUI 不创建该日志。
- 桌面 worker 在就绪前沿用原启动输出和状态通知；就绪通知前调用 `finish_desktop_output()` 将原始 stdout/stderr 转向空输出，释放临时输出文件。运行异常由 Python 日志处理。父启动进程在创建 worker 前释放自身的应用日志句柄，避免父子轮换冲突。
- macOS 启动输出改到 `tmp/macos-startup-<UUID>.log`；成功后关闭父进程持有的输出文件并删除，失败仅保留最近 3 份。运行后异常摘要读取 `logs/pictide.log` 的尾部。Windows 使用同样的临时兜底策略。

## 调用和数据流

```mermaid
sequenceDiagram
    participant Launcher as 现有启动入口
    participant Host as Host / worker
    participant Files as 日志文件
    Launcher->>Host: 启动并接收准备输出
    Host->>Files: 配置应用日志，记录启动和准备阶段
    Host->>Host: 初始化依赖与应用
    Host->>Launcher: 释放原始启动输出后通知 ready
    Launcher->>Launcher: 删除本次临时输出
    Host->>Files: 运行事件、任务状态、异常与退出
```

## 重点关注

- 历史日志不自动删除、迁移或覆盖；新规则只管理新生成的日志和本次临时启动文件。
- 验证放在独立 worktree、数据目录与端口，覆盖真实进程输出轮换、异常落盘、下载失败和生命周期，不运行全量测试或真实 GPU 任务。
- macOS 构建使用 GitHub Actions；当前 Mac 只运行构建好的产物。平台验证结果分别记录。
