# 对外请求跟随系统代理

## 概述

统一模型下载、生图 API、事件流与图片下载的代理规则，互联网跟随系统 HTTP(S) 代理，本机和局域网直连。

## 架构

```mermaid
flowchart LR
    Downloads[既有资源下载] --> Policy[network 内部代理策略]
    Adapters[既有生图适配器 HTTP / WebSocket] --> Policy
    Policy --> Direct[本机 / 私有 IP / 本地域名直连]
    Policy --> System[系统代理与环境变量]
    System --> External[互联网服务]
```

## 职责边界

- 沿用已确认的业务边界。`backend/network.py` 仅提供内部 `proxy_for_url(url)` 与同步 `open_url(request, timeout=...)` 工具；不承载任务状态或生图协议。
- 代理来源沿用 Python 标准库：环境变量优先，其次平台系统 HTTP(S) 代理；遵循标准库的代理绕过规则（含 `NO_PROXY`）。没有可用代理时直连。
- 回环、私有和链路本地 IP、`localhost`、无点的本地主机名及 `.local` / `.lan` 域名始终直连；自定义内网域名可通过绕过列表指定。URL 分类不触发额外 DNS 查询。
- 同步下载在每个跳转目标重新选择代理；异步适配器通过既有 aiohttp 请求的 `proxy` 参数应用同一规则，沿用现有关闭自动跳转的规则。ComfyUI WebSocket 同步适配。
- 本机启动探测保持直接连接；候选、推荐、任务接口和模块边界保持原样。凭据处理、TLS 验证、任务不重复提交和图片下载隔离继续沿用现有机制。

## 调用和数据流

```mermaid
sequenceDiagram
    participant Caller as 下载 / 生图适配器
    participant Policy as 网络工具
    participant OS as 环境与系统配置
    participant Target as 目标服务
    Caller->>Policy: 查询目标 URL 的代理
    Policy->>Policy: 本机 / 局域网判定
    Policy->>OS: 查询代理与绕过列表
    Policy-->>Caller: HTTP(S) 代理地址或直连
    Caller->>Target: 现有客户端发送请求
```

## 重点关注

- 按用户已确认的规则实现，不修改系统代理设置，不新增 GUI 或依赖；PAC 脚本与 SOCKS 解析不在本次范围。
- 使用本机模拟代理、服务和 WebSocket 验证路由及凭据隔离，不调用真实云端生图或 GPU；Mac 验证不改变系统代理配置。


## macOS 系统证书修复（2026-10-20）

用户确认优先修复 Mac 首次 MiniLM 下载的 CA 问题，沿用既有网络工具边界。

- 实机确认：冻结 Python 的 OpenSSL 默认 CA 路径指向构建机器的 `/Library/Frameworks/Python.framework/Versions/3.12/etc/openssl/cert.pem`，目标 Mac 上该文件不存在。已有模型的热启动成功，缺少 MiniLM `config.json` 的真实 HTTPS 下载失败；仅在测试进程指定包内 certifi 后下载成功，确认故障在证书信任源。
- `network.tls_context()` 在 macOS 使用固定版本 `truststore==0.10.5`，由系统 Security.framework 验证证书链与主机名；依赖只在 macOS 安装。同步下载、Host 生图会话（含 ComfyUI WebSocket）和隔离的云端图片下载共用此上下文。Windows/Linux 沿用 Python 默认上下文。
- 不使用全局 SSL 注入，不额外载入 certifi 根证书，不修改系统证书或代理设置。旧的补充 certifi 方案保持未集成。
- 验证重点：可信 MiniLM HTTPS 下载、陌生自签名证书拒绝、代理路由与凭据隔离。最终安装包由 GitHub Actions 构建，再在用户 Mac 的独立目录运行；该 Mac 不承担构建工作。
### 验证结果

- Windows 本地网络冒烟 6 项通过，macOS 专项 1 项按平台跳过；受影响的 Mac 归档模拟检查通过。
- [最终 Intel Actions 构建](https://github.com/Lykr/pictide/actions/runs/39419529286)通过，构建源码为 `511f458705b21d559cc889bac7f62e9efbcbef89`。macOS 自签名证书拒绝检查、原生构建、包签名、依赖许可和首次 MiniLM 下载及启动冒烟均通过。后续提交仅补充模拟样例和本验证记录，不改变包内运行代码。
- 同一 ZIP 在用户 Intel Mac / macOS 15.8.1 校验 SHA-256 后通过系统解压、签名、运行库加载、启动器自检和独立数据启动检查。
- 包内服务入口成功复现并修复缺少 `config.json` 的原故障；进一步在空模型目录通过现有系统 HTTP(S) 代理下载全部 5 个文件，共 91,102,036 字节，逐一通过大小与 SHA-256 校验后启动 HTTP，完整准备约 217 秒。测试移除 `SSL_CERT_FILE` / `SSL_CERT_DIR`，未额外载入 CA 文件。
- 包内生图客户端拒绝不可信自签名 HTTPS 服务；模拟云端检查、生成、图片下载的代理路由与 API 凭据隔离通过。未调用真实生图服务或 GPU。
- 所有自有服务和模拟端口已关闭；系统证书、代理配置及个人数据保持原状。本轮覆盖 Intel 包，Apple Silicon 尚未进行本次专项实机验证；未创建版本标签或发布 Release。
- 实机报告保存在 `dev/verification/macos-system-trust-20261020/`。本地最终包为 `releases/pictide-0.4.0-darwin-x86_64.zip`，72,545,506 字节，SHA-256 为 `3c34f4584096d9f7054a4c9a0ec2d98b2695a375037d96816a6932359a69ec6f`；原本地 Mac 包已备份至该验证目录的 `previous-release/`。
