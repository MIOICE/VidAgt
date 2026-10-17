# VidAgt 阶段验收清单

更新日期：2026-10-08

状态说明：✅ 已验证；🟡 已实现、待业务样例或压力联调；⬜ 未开始。

可随时执行基础验收脚本：

```powershell
.\scripts\verify.ps1
```

## 里程碑 A：工程与接口

- ✅ 后端目录、配置、数据模型和 API Schema 已建立。
- ✅ 47 个 Python 源文件通过 AST 语法检查。
- ✅ Ruff 全量检查通过。
- ✅ Pytest 24 项测试通过，覆盖数据契约、媒体融合、跨段检索、令牌桶、对话记忆、URL 安全、对象存储及健康接口。
- ✅ FastAPI 可完整导入并生成包含 19 个路径的 OpenAPI Schema。
- ✅ SQLAlchemy 全量模型可在内存数据库完成建表。
- ✅ Vue/TypeScript 生产构建通过，Vite 已生成部署产物。
- ✅ MySQL 8.4 自动建表与健康检查通过（宿主端口默认 3307）。
- ✅ MinIO 数据卷权限、Bucket 初始化兼容路径及 HTTP 健康检查通过；跨域使用服务端白名单配置。
- ✅ FastAPI 就绪接口与 OpenAPI 页面分别在 `/api/v1/health/ready`、`/docs` 返回 HTTP 200。

验收命令：

```powershell
docker compose up --build mysql redis minio api
Invoke-RestMethod http://localhost:8000/api/v1/health/ready
Start-Process http://localhost:8000/docs
```

期望：健康接口返回 `status=ready`，OpenAPI 中存在 uploads、videos、tasks、analyses、chat 和 chat history 接口。

## 里程碑 B：上传与媒体解析

- ✅ 预签名分片直传与合并已通过 6,869,624 字节真实 MP4 上传；中断后的缺失分片续传仍待专项验收。
- 🟡 链接导入及 2GB 上限。
- ✅ 58.866 秒 HEVC 真实视频已完成 FFmpeg 探测/转码、音频提取、faster-whisper 转写、关键帧视觉理解、融合与索引，任务终态 `COMPLETED`、视频终态 `READY`。
- 🟡 Redis WatchDog 式内容锁和 SHA-256 去重。
- 🟡 任务进度 SSE 与失败重试（当前为任务入口重跑，非中间结果级阶段恢复）。

验收步骤：

1. 打开 `http://localhost:8080`，上传一个 1–5 分钟 MP4。
2. 上传到一半刷新页面，重新选择同一文件，确认从缺失分片继续。
3. 观察任务阶段从 `PROBING` 推进到 `COMPLETED`。
4. 再次上传同一文件，确认第二个视频复用现有 VideoContext。
5. 在视频工作区播放预览并查看带时间戳转写。

## 里程碑 C：Agent

- ✅ 百炼文本、视觉、Embedding 与 JSON Schema 输出已分别通过在线调用；真实视频自动结构化报告已完成，状态 `COMPLETED`、进度 100%。
- 🟡 Planner–Executor–Critic：结构化 Critic 反馈 + 两轮成本上限；尚未接入独立离线评估器。
- 🟡 自定义分析目标。
- ✅ 连续追问的最近 12 条消息记忆与 6000 字符裁剪逻辑通过测试。
- ✅ 对话与证据持久化，前端刷新后可恢复最近会话（待容器联调）。
- 🟡 报告与问答中的证据 ID、来源和时间戳。

验收步骤：

1. 确认百炼 `qwen3.8-27b` 与 `text-embedding-v4` 保持可用（当前已通过最小调用）。
2. 视频处理完成后等待自动报告生成。
3. 创建“提取全部行动项并按优先级排序”的自定义分析。
4. 追问一个视频未涉及的问题，确认系统明确提示证据不足。
5. 点击问答证据标签，确认播放器跳转到对应时间。

## 里程碑 D：工程质量

- ✅ Ruff 与 Pytest。
- ✅ 前端依赖使用 lockfile 固定，esbuild 安装脚本进入显式白名单。
- ✅ 前端 TypeScript 检查与 Vite 生产构建。
- ✅ Element Plus 按需注册与路由懒加载；主入口 JS 约 1.13MB → 321KB，CSS 约 373KB → 103KB（Vite minified 输出口径）。
- ✅ Redis Lua 令牌桶测试通过；文本、视觉和 Embedding 模型调用均配置指数退避重试。
- ✅ URL 导入拦截回环、私网、链路本地及保留地址，并在 API/Worker 两阶段校验。
- ✅ CPU Compose 核心运行栈、百炼三类模型及 58.866 秒真实视频媒体处理链路均已联调。
- 🟡 RTX 4050 GPU Worker 联调。
- ⬜ 2GB 文件和 3 小时视频压力测试。
- ⬜ 处理阶段检查点、按窗口增量持久化和断点恢复。
- ⬜ 20 个相同内容并发提交去重测试。
- ⬜ 根据实测结果填写简历中的性能提升数据。

Docker Desktop、WSL2 Linux Engine 与 Compose 已完成可用性检查；项目已将 Node、固定版本静态 FFmpeg/FFprobe 和 Python 媒体依赖封装到容器中。2026-10-08 实测前端、API 文档、API 就绪探针和 MinIO 探针均返回 HTTP 200；58.866 秒 HEVC 真实视频完成转码、ASR、视觉理解、融合、索引及自动结构化报告；阿里云百炼文本、视觉、1024 维 Embedding 和结构化 JSON 调用通过。下一步完成证据跳转、连续追问及断点续传专项验收。
