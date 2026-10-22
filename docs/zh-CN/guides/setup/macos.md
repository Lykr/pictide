# macOS 安装与启动

[English](../../../guides/setup/macos.md)

[安装与接入](../getting-started.md) · [用户文档](../../index.md)

## 便携版本

以下步骤适用于 v0.5.0 及后续版本的 `.app` 包。

解压与 Mac 芯片匹配的 ZIP（Apple Silicon 或 Intel），将 `Pictide.app` 拖入「应用程序」并打开。首次启动的小准备窗口会显示[推荐依赖下载](../getting-started.md#推荐依赖准备)进度，就绪后自动打开浏览器。接下来[连接生图服务](../getting-started.md)，开始漫游。

准备失败时，点击「重试」继续，已下载的文件会保留使用。「查看日志」打开数据目录中的 `logs/pictide.log`；应用日志尚未生成时，打开本次启动的临时输出。

关闭网页后程序继续运行。通过菜单栏图标可以重新打开 Pictide、复制访问地址、打开数据目录、查看日志或退出，也能看到准备进度和服务停止等状态。提示跟随系统语言，支持简体中文，其余语言默认英文。

应用暂未使用 Developer ID 签名或经过 Apple 公证。如果首次打开被拦截，尝试打开后按 Apple 的[「仍要打开」步骤](https://support.apple.com/zh-cn/102445)，在「系统设置 → 隐私与安全性」允许打开。Pictide 不修改系统安全设置。

个人数据保存在 `~/Library/Application Support/Pictide/`，替换应用会保留图片和偏好。从旧包迁移时，先退出两个版本，按[备份与恢复](../backup.md#备份与恢复)保存并复制个人数据到新位置，检查完成前保留旧副本。

## 局域网访问

打开终端，运行：

```bash
/Applications/Pictide.app/Contents/MacOS/Pictide --lan
```

手机连接同一局域网，打开 Pictide 菜单中的局域网地址。参见[局域网与主屏幕应用](../access.md)。

## 端口与数据目录

需要换端口或数据位置时：

```bash
/Applications/Pictide.app/Contents/MacOS/Pictide --port 8191 --data-dir "$HOME/PictideData"
```

加 `--cli` 使用终端模式，按 Ctrl+C 停止。

## 从源码准备

先按[macOS 源码准备](../../dev/setup/macos.md#从源码准备)安装环境并构建前端，再在项目目录运行 `./start.command`。源码启动保留终端，默认使用项目内 `data/`；可按需添加 `--lan`、`--port` 或 `--data-dir`。

源码启动需要 Python 3.10+。若源码启动脚本缺少执行权限，在项目目录运行 `chmod +x start.sh start.command`。构建发行包见[开发文档](../../dev/setup/macos.md#构建便携包)。

## 更新

应用安装在其他位置时，请调整命令中的路径。`--check-updates` 只检查；`--update` 显式请求兼容版本的下载、安装与重启，不会自动更新。

```shell
/Applications/Pictide.app/Contents/MacOS/Pictide --check-updates
/Applications/Pictide.app/Contents/MacOS/Pictide --update
```

请先保存编辑并等待生图任务结束。无法直接安装时，通过 [GitHub Releases](https://github.com/Lykr/pictide/releases) 手动更新；应用内操作见[通用设置](../settings.md#通用设置)。
