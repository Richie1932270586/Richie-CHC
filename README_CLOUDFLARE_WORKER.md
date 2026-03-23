# Cloudflare Worker Editor

这个项目现在可以把“项目案例 / 实习与实践经历”的增删能力部署到 `Cloudflare Workers`，这样你不需要每次本地启动 Python 后端。

## 1. 这套方案会做什么

- 你的网页前端继续保留现有的新增 / 删除 / 密码解锁交互
- `Cloudflare Worker` 负责校验密码、签发短时编辑令牌
- Worker 通过 GitHub Contents API 更新 [data/site-content.json](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/data/site-content.json)
- GitHub 仓库生成 commit，GitHub Pages 随后更新

## 2. 需要准备什么

- 一个 Cloudflare 账号
- 一个 GitHub Personal Access Token
- GitHub token 至少要有目标仓库的 `Contents: Read and write`

推荐用 GitHub `fine-grained token`：

- Repository access: `Only select repositories`
- Repository: `Richie-CHC`
- Repository permissions: `Contents -> Read and write`

## 3. 安装和登录 Wrangler

先在本机安装 Node.js，然后执行：

```powershell
npm install -g wrangler
wrangler login
```

如果你不想全局安装，也可以用 `npx wrangler` 替代下面的 `wrangler` 命令。

## 4. 检查 Worker 配置

基础配置已经写在 [wrangler.toml](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/wrangler.toml)，Worker 入口在 [cloudflare_worker/worker.js](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/cloudflare_worker/worker.js)：

- `GITHUB_OWNER = "Richie1932270586"`
- `GITHUB_REPO = "Richie-CHC"`
- `GITHUB_BRANCH = "main"`
- `EDITOR_CONTENT_PATH = "data/site-content.json"`

如果你的 GitHub Pages 地址变化了，把 `EDITOR_ALLOWED_ORIGINS` 一并改掉。

## 5. 写入 Secrets

下面这三个值不要写进仓库文件，要用 Cloudflare Secret：

```powershell
wrangler secret put GITHUB_TOKEN
wrangler secret put EDITOR_PASSWORD
wrangler secret put EDITOR_TOKEN_SECRET
```

执行每条命令后，终端会提示你输入对应值。

说明：

- `GITHUB_TOKEN`：GitHub PAT
- `EDITOR_PASSWORD`：你网页里“解锁编辑”时输入的密码
- `EDITOR_TOKEN_SECRET`：一段很长的随机字符串，用于签发短时编辑令牌

如果你更想存密码哈希，也可以不设 `EDITOR_PASSWORD`，改用：

```powershell
wrangler secret put EDITOR_PASSWORD_HASH
```

这个哈希值应为密码的 SHA-256 十六进制字符串。

## 6. 部署 Worker

在项目根目录执行：

```powershell
wrangler deploy
```

部署完成后，Cloudflare 会返回一个 Worker 地址，通常形如：

```text
https://richie-portfolio-editor.<你的子域>.workers.dev
```

## 7. 把前端指向 Worker

编辑 [config.js](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/config.js)，把 `PORTFOLIO_EDITOR_API_BASE` 改成你的 Worker 地址，例如：

```js
window.PORTFOLIO_EDITOR_API_BASE = "https://richie-portfolio-editor.your-subdomain.workers.dev";
window.PORTFOLIO_CONTENT_URL = "data/site-content.json";
```

然后把改完的前端代码推到 GitHub Pages。

## 8. 本地联调

如果你想先本地看 Worker：

```powershell
wrangler dev
```

默认会给你一个本地调试地址。你可以临时把 [config.js](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/config.js) 指到那个地址，再测试解锁、新增、删除。

## 9. 你以后怎么用

部署完成后，你只需要：

1. 打开网页
2. 点击 `解锁编辑`
3. 输入你设置的编辑密码
4. 直接新增或删除项目 / 经历

以后不需要再手动开本地 Python 后端。

## 10. 限制

- 这套同步只会写 [data/site-content.json](/c:/Users/陈慧驰/Downloads/Richie-CHC%20(1)/Richie-CHC/data/site-content.json)
- 它不会自动创建 `projects/xxx/index.html`
- 如果你新增项目卡片，最好先确认对应项目页面已经存在
