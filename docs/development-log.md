# VidAgt 开发日志

## 2026-10-08：Docker 全栈启动与媒体链路冒烟验收

### 本轮完成

- 修复 Windows 虚拟化、WSL2 与 Docker Desktop 启动问题，并将 Docker WSL 数据盘迁移到 `E:\DockerData\wsl`；原有镜像和数据卷保留。
- MySQL 宿主映射端口调整为可配置的 `MYSQL_HOST_PORT`，默认使用 3307，避免占用本机 3306。
- 为 MinIO 增加数据卷权限初始化容器、HTTP 健康探针和服务端 CORS 白名单；后端兼容不实现 Bucket CORS API 的对象存储版本。
- 后端补充 MySQL 8 `caching_sha2_password` 所需的 `cryptography` 依赖。
- 媒体镜像改用 Digest 固定的静态 FFmpeg 7.1/FFprobe，多阶段复制替代 Debian apt 安装，规避 CDN 抖动并减少无关图形系统依赖。
- 优化后端 Docker 分层：基础依赖、媒体可选依赖与业务源码分层缓存，业务代码变更不再触发全部依赖重装。
- 完成阿里云百炼 OpenAI-Compatible 接入：`qwen3.8-27b` 同时承担文本与视觉任务，`text-embedding-v4` 输出 1024 维向量；针对百炼 Embedding 仅接受字符串数组的约束关闭 LangChain Token 预编码。
- 对 Qwen3 系列统一关闭默认 Thinking，保证 Planner、Critic 等结构化 JSON 输出稳定。

### 可复核结果

| 项目 | 结果 |
|---|---|
| Docker Compose 服务 | API、前端、MySQL、Redis、MinIO、Agent Worker、Media Worker 均启动 |
| 健康接口 | API live/ready、Swagger UI、前端、MinIO 均 HTTP 200 |
| 媒体容器 | FFmpeg 7.1、FFprobe 7.1、faster-whisper、OpenCV headless 可用 |
| 媒体冒烟 | 1 秒 H.264 视频探测、WAV 提取、关键帧落盘通过 |
| 后端测试 | 26 passed |
| Ruff | 通过 |
| 前端 | Docker 内 pnpm production build 通过 |
| 百炼文本模型 | 最小文本请求返回 `OK` |
| 百炼视觉模型 | 正确识别合成图中的红框及 `VIDAGT` 文字 |
| 百炼 Embedding | `text-embedding-v4` 返回 1024 维向量 |
| 结构化输出 | JSON Schema 最小调用通过 |

### 验收边界

- 阿里云百炼文本、视觉、Embedding 与结构化 JSON 单项调用已实测；真实视频自动报告已进入在线链路验收。
- `faster-whisper` 已完成真实视频首次模型下载与转写；当前仅完成单样例功能验收，准确率与吞吐量尚未评测。
- 尚未完成 2GB/3 小时压力测试、AI 阶段级断点恢复和 20 路相同内容并发去重测试，简历不应写成已验证指标。

### 真实视频链路修复与验收

- 修复 API 容器重建后 Nginx 缓存旧容器 IP 导致的 `502 Bad Gateway`：前端代理改用 Docker 内置 DNS（`127.0.0.11`）动态解析 `api` 服务。
- Celery 异步任务改为每个 Worker 线程复用长期事件循环，避免 SQLAlchemy/HTTP 连接池跨 `asyncio.run` 新循环复用时报 `Future attached to a different loop`。
- 将 PyAV 固定为 `>=11,<19`；PyAV 19 移除了 `metadata_errors` 参数，与 faster-whisper 1.2.1 尚不兼容。
- 使用上传视频 `f78eec12-b6f7-4f13-b353-b399ea739559` 完成真实链路验收：文件 6,869,624 字节、时长 58.866 秒、HEVC 720×1280。
- 处理任务 `c2804294-212a-4072-b1bf-c0588683ffd3` 已完成探测、转码、音频提取、ASR、关键帧视觉理解、融合与索引，终态为 `COMPLETED`，视频终态为 `READY`。
- 自动报告 `cee36919-7363-486c-bca2-c5be9e703319` 完成 Planner–Executor–Critic 全链路，终态为 `COMPLETED`、进度 100%，Worker 实测耗时约 100.8 秒。
- 经前端 Nginx 代理访问健康接口和视频接口均返回 HTTP 200；容器内事件循环连续调用与 PyAV/faster-whisper 版本检查通过。

## 2026-09-25：MVP 工程闭环

### 本轮完成

- 完成 Vue 3 + TypeScript 生产构建，修复组合式 TypeScript 配置的 `noEmit` 约束。
- 使用 pnpm 11.19.0 lockfile 固定依赖，并将 esbuild 安装脚本纳入项目级白名单。
- Docker 前端镜像切换为 Corepack + pnpm frozen lockfile 构建。
- 增加根目录 `.dockerignore`，避免 `.venv`、`node_modules`、模型与构建产物进入 Docker Context。
- Element Plus 改为按需注册，Home/Workspace 页面改为动态导入。
- 新增 FastAPI ASGI 健康接口测试，覆盖存活、就绪和 Redis 故障三个路径。
- 修复非连续 Top-K 语义块检索夹带区间数据的问题，并增加 SQLite 集成测试。
- 实现最近消息对话记忆、历史恢复接口与前端会话恢复。
- 固定窗口限流升级为 Redis Lua 令牌桶，模型重试覆盖文本、视觉和 Embedding。
- URL 导入增加 API/Worker 两阶段公网地址校验，拦截 SSRF 常见目标。
- MinIO 镜像固定到官方发布版本，CORS 配置改为 `mc` 支持的 S3 XML 格式。
- 一键验收脚本升级为 5 个阶段，同时检查 Python、配置文件、Compose、后端和前端。

### 可复核结果

| 项目 | 结果 |
|---|---|
| Python AST | 47 个文件，0 错误 |
| Ruff | 通过 |
| Pytest | 当时 21 passed；当前累计 26 passed |
| OpenAPI | 19 paths |
| Vue TypeScript | 通过 |
| Vite production build | 通过 |
| 前端主入口 | 321KB，gzip 116KB |
| Docker Compose 运行联调 | 详见 2026-10-08 记录 |

运行联调修复：MySQL 宿主端口改为可配置的 `MYSQL_HOST_PORT`（默认 3307）；
MinIO 增加非 root 数据卷权限初始化与 HTTP 健康探针；后端补充 MySQL 8
`caching_sha2_password` 所需的 `cryptography` 依赖。

### 下一验收门槛

安装 Docker Desktop 后执行：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

随后按 `docs/acceptance.md` 完成 1–5 分钟样例视频、断点续传、内容去重、报告与追问验收。没有实测前，不把 2GB/3 小时、并发去重与 Token 节省写成已验证指标。
