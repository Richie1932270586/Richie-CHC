# Cloudflare Worker Backend

Worker 入口文件在 [worker.js](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/cloudflare_worker/worker.js)。

它实现了与本地 Python 后端一致的接口：

- `GET /api/health`
- `GET /api/content`
- `POST /api/auth/verify`
- `POST /api/projects`
- `DELETE /api/projects/:id`
- `POST /api/experiences`
- `DELETE /api/experiences/:id`

部署说明见 [README_CLOUDFLARE_WORKER.md](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/README_CLOUDFLARE_WORKER.md)。
