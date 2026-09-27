# 杭州 ECS 试点部署与恢复手册

本手册适用于不超过 10 台受邀设备、同时约 1–3 人使用的单机试点。上线前先准备杭州 ECS（Ubuntu 24.04 x86_64、2 核 4 GiB、60 GiB ESSD Entry、10 Mbps 峰值）、正式域名、受信任证书、模型密钥、发布签名、杭州私有 OSS 桶及 ECS RAM 角色。中国内地部署还需按实际分发方式完成适用的域名与 [App 备案](https://help.aliyun.com/zh/icp-filing/basic-icp-service/getting-started/quick-sta-rt-for-icp-filing-for-personal-app)。服务器购买价格以阿里云控制台为准。

## 1. 云资源与边界

- 安全组仅对公网放行 443 和证书验证/HTTP 跳转所需的 80；22 仅允许运维来源地址。8000、Docker socket、OSS 桶不能公网访问。
- 私有 OSS 桶位于杭州，关闭版本控制与公开 ACL；给 ECS [RAM 角色](https://help.aliyun.com/zh/ecs/user-guide/attach-an-instance-ram-role-to-an-ecs-instance)仅授予该桶 `guojing/<deployment_id>/authorization/*` 的列举、上传、下载、删除权限及读取桶 ACL/版本控制权限。不要给 APK、API 或配置文件写长期 OSS AccessKey。
- 为受邀安装准备签名 APK。新版后端拒绝旧客户端的匿名请求，须同时切换客户端。签名密钥保留在发布者的受限目录，不上传服务器。
- 运维先提供 HTTPS 告警接收地址，接受 JSON `{"service":"guojing","issues":["code"]}`。告警接收服务自身需要另行配置实际通知渠道。

OSS 官方 Python SDK 提供 [ECS RAM 角色自动刷新临时凭据](https://www.alibabacloud.com/help/en/oss/developer-reference/2-0-manual-preview-version/)。沙箱限额要求 rootless Docker、cgroup v2、systemd 与 CPU/内存/PID 控制器委派，见 [Docker 官方说明](https://docs.docker.com/engine/security/rootless/tips/)。上线脚本会创建一个临时沙箱，读取内核实际 cgroup 值，并检查只读根文件系统；不通过就不切换版本。

## 2. 首次初始化

从可信构建机把本仓库的发布文件上传到服务器 `/opt/guojing/releases/<版本号>/`。目录由 root 拥有、不可由服务用户写入；不要传 `.env.local`、密钥、缓存、APK 或数据库。先在新 ECS 以 root 运行：

```sh
cd /opt/guojing/releases/<版本号>
bash deploy/bootstrap-ecs.sh
```

脚本安装 Nginx、certbot、rootless Docker 依赖、固定版 uv 与 Python 3.12.13；关闭 rootful Docker 服务，创建 `guojing` 用户、持久化目录和 systemd 单元。检查 `systemctl --user` 下的 rootless Docker 服务已为 `guojing` 用户启动。`id -u guojing` 给出 socket 路径中的 UID。

将 [`deploy/production.env.example`](../deploy/production.env.example) 复制到 `/etc/guojing/production.env`，填入模型 key、`unix:///run/user/<UID>/docker.sock`、固定镜像 digest、杭州私有桶、RAM 角色及告警地址，再执行：

```sh
chown root:guojing /etc/guojing/production.env
chmod 0640 /etc/guojing/production.env
```

环境文件是 `KEY=value` 数据，不会由 shell 求值。密钥不进 Git、不写命令行。先用 rootless Docker 在本地 socket 拉取经审核的镜像，再把 `docker image inspect` 输出的完整 `registry/repository@sha256:<digest>` 写入配置。API 进程不会通过网络拉取镜像；它只使用本地 Unix socket。设置 `GUOJING_DEPLOYMENT_ID` 为本部署固定标识，以便启动时仅清理本部署标签的遗留容器。Docker 沙箱保持 `network=none`、只读根、无宿主机挂载与无凭据。

先将 API DNS A 记录指向 ECS，开放 80/443，再执行：

```sh
bash deploy/install-ingress.sh api.example.com ops@example.com
```

该脚本用 HTTP webroot 验证域名、安装受信任证书，并启用 certbot 自动续期钩子。Nginx 上传与 SSE 均关闭缓冲和缓存，以 HTTP/1.1 转发；Nginx 关闭访问日志。配置根据 [Nginx `proxy_request_buffering`](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) 的行为设置，超过 12 MiB 的实际字节仍由 API 检查。

首次版本切换前应确认数据库文件 `/var/lib/guojing/data/guojing.db` 不存在，即创建空数据库。然后：

```sh
bash deploy/release.sh /opt/guojing/releases/<版本号>
curl -fsS https://api.example.com/ready
bash deploy/admin.sh invite --label invited-device-1
```

发布脚本锁住发布操作、冻结依赖、运行迁移、验证真实沙箱限制、切换符号链接、启动单个 Uvicorn 进程。匿名创建会话必须返回 401；`/health` 和 `/ready` 必须为 200。`/internal/status` 只可从服务器本机 `127.0.0.1:8000` 读取，公网路径由 Nginx 拒绝。

## 3. 发布、回滚与恢复

平时使用 `bash deploy/admin.sh <命令>`，可创建邀请码、列出设备、查看当日用量、`revoke <device_id>`、`limit <device_id|global> <次数>`、`pause`、`drain` 和 `resume`。设备停用立即拒绝新请求；后台在 15 秒内取消它的未完成任务。人工升级按“预备只读新版本 → 暂停新分析 → 等待最多 125 秒或终止在途任务 → 停服务 → 备份授权和用量 → 迁移 → 真实沙箱/本机检查 → 切换并恢复接入”进行：

```sh
bash deploy/release.sh /opt/guojing/releases/<新版本号>
```

失败时保持暂停。检查 `journalctl -u guojing -n 100 --no-pager`，修复后再次发布或回滚：

```sh
bash deploy/rollback.sh
```

回滚脚本仅允许目标版本包含设备准入迁移，防止旧匿名版本删除设备表；如新迁移无法安全向后降级，应由维护者审查迁移后再回滚。整机重建时先按同版本初始化空数据库并迁移，停止 API 后执行：

```sh
bash deploy/admin.sh restore --oss-key 'guojing/<deployment_id>/authorization/<备份对象>.json'
bash deploy/admin.sh devices
bash deploy/admin.sh usage
bash deploy/admin.sh resume --reconciled
```

恢复文件也可用 `restore --file /受限目录/backup.json`。仅能恢复到空数据库；恢复会话不在备份中，用户需重新开始。恢复时默认暂停接入，运维核对设备授权和当天额度后才能解除。故障后人工恢复目标 4 小时。

## 4. 留存、告警与上线门禁

systemd 每 6 小时运行 `guojing-backup.timer`，每分钟运行 `guojing-prune.timer` 清除满 24 小时的 OSS 授权快照；`guojing-monitor.timer` 每分钟检查 API 依赖、内存/磁盘超过 80%、连续 3 次分析失败及备份滞后。监控输出仅包含队列长度、计数、tokens、耗时和错误码。会话文本不进入 OSS，数据库中创建满 24 小时的会话每分钟删除，并执行 WAL 截断。生产关闭公开 API 文档与 Uvicorn 访问日志。

- `GUOJING_RUN_DOCKER_TESTS=1 uv run pytest -q tests/infrastructure/sandbox/test_docker_integration.py`：真实容器限额、隔离与文件操作。
- 使用固定生产配置运行付费合成评测：状态正确率 ≥90%，目标框 IoU≥0.5 的比例 ≥80%。模型 `deepseek-flash` 仍可通过配置替换，见 [DeepSeek 视觉模型说明](https://api-docs.deepseek.com/guides/vision/)。
- 两台以上真机验证多轮、断网恢复和 3 人同时使用；10 个模拟并发请求验证明确过载、最多 2 个分析和 8 个等待，且后续任务可继续。
- 先邀请 3 人试用 48 小时，确认无任务卡死、内存持续增长和额度失控，再逐步开放至 10 人。每次发布允许短暂停机。

费用按 ECS、流量、域名、少量备份存储与实际模型 tokens 核算；每日次数上限并不是固定金额上限。语音输入与应用市场发布不在本次试点交付范围内。
