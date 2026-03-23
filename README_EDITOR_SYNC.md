# Portfolio Editor Sync

这个项目现在支持通过独立后端把项目 / 经历的增删操作同步到 GitHub 仓库。

推荐方案：

- 线上长期使用：部署 [Cloudflare Worker](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/cloudflare_worker/worker.js)
- 本地临时调试：继续使用 [editor_backend/server.py](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/editor_backend/server.py)

Cloudflare Worker 的完整部署说明见 [README_CLOUDFLARE_WORKER.md](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/README_CLOUDFLARE_WORKER.md)。

## 1. 配置前端 API 地址

编辑 [config.js](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/config.js)：

```js
window.PORTFOLIO_EDITOR_API_BASE = "https://你的-worker.workers.dev";
window.PORTFOLIO_CONTENT_URL = "data/site-content.json";
```

如果只是本地测试，也可以改回 `http://127.0.0.1:8787`。

## 2. 配置后端环境变量

本地 Python 后端文件在 [editor_backend/server.py](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/editor_backend/server.py)。

至少需要这些环境变量：

- `GITHUB_TOKEN`
- `GITHUB_OWNER`
- `GITHUB_REPO`
- `GITHUB_BRANCH`
- `EDITOR_PASSWORD` 或 `EDITOR_PASSWORD_HASH`
- `EDITOR_TOKEN_SECRET`
- `EDITOR_ALLOWED_ORIGINS`

推荐示例：

```powershell
$env:GITHUB_TOKEN="你的GitHub令牌"
$env:GITHUB_OWNER="Richie1932270586"
$env:GITHUB_REPO="Richie-CHC"
$env:GITHUB_BRANCH="main"
$env:EDITOR_PASSWORD="你自己的编辑密码"
$env:EDITOR_TOKEN_SECRET="请换成一段足够长的随机字符串"
$env:EDITOR_ALLOWED_ORIGINS="https://richie1932270586.github.io"
python .\editor_backend\server.py
```

如果你想用密码哈希而不是明文密码，可以改用 `EDITOR_PASSWORD_HASH`，值为密码的 SHA-256 十六进制串。

## 3. 内容数据文件

项目和经历的同步目标是：

- [data/site-content.json](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/data/site-content.json)

前端页面会优先读取这个 JSON，再渲染项目卡片和经历卡片。

## 4. 工作方式

1. 页面点“解锁编辑”
2. 输入密码
3. 前端向后端换取短时编辑令牌
4. 新增/删除项目或经历
5. 后端通过 GitHub API 更新 `data/site-content.json`
6. GitHub 生成新的 commit，GitHub Pages 随后更新

## 5. 注意

- 这套方案不会自动创建新的 `projects/xxx/index.html` 文件，只会同步首页的数据卡片。
- 如果你新增了项目卡片，最好先确保对应链接页面已经存在。
- 如果站点仍部署在 GitHub Pages，而后端是单独部署的服务，请务必使用 HTTPS 后端地址并配置 `EDITOR_ALLOWED_ORIGINS`。
