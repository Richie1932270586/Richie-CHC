# Richie-CHC GitHub Pages 部署说明

## 现在这个版本包含什么
- 首页个人网站 `index.html`
- 样式文件 `styles.css`
- 头像：`assets/avatar.png`
- 中文简历：`assets/chenhuichi_resume_cn.pdf`
- 产品 Demo 子页面：
  - `projects/ops-copilot/index.html`
  - `projects/flowguard-ai/index.html`

## 本地预览
直接双击 `index.html` 即可打开首页。

## 部署到 GitHub Pages
1. 登录 GitHub，新建一个公开仓库，名称填 `Richie-CHC`
2. 把本文件夹里的所有内容上传到仓库根目录
3. 进入仓库 `Settings` → `Pages`
4. 在 `Build and deployment` 中选择：
   - Source: `Deploy from a branch`
   - Branch: `main`
   - Folder: `/ (root)`
5. 保存后等待几分钟

## 预计网站链接
https://richie1932270586.github.io/Richie-CHC/

## 更新网站
以后想更新内容：
1. 修改本地文件
2. 重新上传替换 GitHub 仓库中的文件
3. 等 1–3 分钟自动刷新
