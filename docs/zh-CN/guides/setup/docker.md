# Docker 部署

[English](../../../guides/setup/docker.md)

[安装与生图 API 接入](../getting-started.md) · [用户文档](../../index.md)

Docker 运行 Pictide 的网页和 CPU 推荐服务。在设置中连接已有的 ComfyUI 或云端生图 API；ComfyUI 和生图模型独立运行。

## 使用 Compose 启动

从 [GitHub Releases](https://github.com/Lykr/pictide/releases/latest) 下载 `compose.yaml`，放进空目录，在该目录执行：

```shell
docker compose up -d
docker compose logs -f pictide
```

打开 [http://localhost:8189](http://localhost:8189)。Compose 自动下载预构建镜像，并选择适合机器的 Linux amd64 或 arm64 架构，无需下载源码或安装编译工具。发布页的 Compose 文件固定对应版本；仓库里的 Compose 文件跟随最新稳定版。

首次启动会下载并校验默认的 **filtered** 词库和 MiniLM，准备完成后开放网页。在此之前，容器健康状态为 `starting`。后续启动复用数据卷中的资源，中断的下载可以续传。镜像包含程序和构建好的前端，不包含词库数据库或模型权重。

每个版本的便携包和两种架构的 Docker 镜像都从同一个 tag 对应的 commit 构建，验证通过后统一发布。

## 数据与配置

Compose 创建 `pictide-data` 命名卷，挂载到 `/data`，保存设置、图片、反馈、词库、模型和日志。停止或重建容器会保留该卷。更新时保持 Compose 文件所在目录不变，以便继续使用同一个卷。

在 `compose.yaml` 旁创建 `.env` 可修改配置：

```dotenv
PICTIDE_PORT=8189
PICTIDE_BIND=127.0.0.1
PICTIDE_VOCABULARY=filtered
```

默认仅本机可以访问。需要在可信局域网使用时，将 `PICTIDE_BIND` 设为 `0.0.0.0`。`PICTIDE_PORT` 修改宿主机端口，容器内仍为 8189。

没有有效词库时，可用 `PICTIDE_VOCABULARY=all-ratings` 指定完整版本。**all-ratings 有可能生成露骨内容。** 已有有效词库会继续使用，详见[词库版本](../vocabularies.md)。

镜像以 `10001:10001` 身份运行。如需把 `pictide-data:/data` 改成宿主机目录，确保该目录允许此用户写入，或将 Compose 的 `user` 设为目录所有者的数字 UID/GID。每个运行中的 Pictide 实例使用独立的数据目录。

## 连接生图 API

在 Pictide 设置中填写 API 地址：

| 服务位置 | 示例 |
| --- | --- |
| Docker 宿主机 | `http://host.docker.internal:8188` |
| 局域网其他机器 | `http://192.168.1.20:8188` |
| 同一 Docker 网络内的其他容器 | `http://comfyui:8188` |

Compose 已为 Linux 配置宿主机网关。Linux 宿主机上的 ComfyUI 需要监听容器可访问的地址，例如使用 `--listen 0.0.0.0` 启动。容器内的 `localhost` 指向 Pictide 容器自身。

## 更新与停止

将新版本发布页的 `compose.yaml` 下载到原目录，保留 `.env`，然后执行：

```shell
docker compose pull
docker compose up -d
```

Docker 通过替换镜像更新，数据卷继续保留。停止容器：

```shell
docker compose down
```

## 下载镜像文件

如果 Docker 主机无法访问 GHCR，可以从同一发布页下载适合机器架构的 `pictide-VERSION-linux-amd64-docker.tar.gz` 或 `pictide-VERSION-linux-arm64-docker.tar.gz`，以及 `compose.yaml`。传到目标机器后执行：

```shell
docker load -i pictide-0.10.0-linux-amd64-docker.tar.gz
docker compose up -d --pull never
```

镜像文件与仓库中经过验证的镜像一致。首次准备词库和 MiniLM 仍需联网。`SHA256SUMS` 用于校验下载文件。工程信息统一保存在 `release-diagnostics.zip`，其中的 `release.json` 记录源码 commit 和镜像摘要，其他 JSON 保存构建与测试报告。

## 从源码构建

开发时可以克隆仓库，通过覆盖配置自行构建：

```shell
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

此方式构建本地的 `pictide:local` 镜像。普通部署使用预构建镜像即可。
