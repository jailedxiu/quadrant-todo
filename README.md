# 四象限待办（Microsoft To Do）

单文件 `index.html`，无需构建。通过 Microsoft Graph 读写你的 To Do，自动创建四个列表：重要紧急、重要不紧急、紧急不重要、不重要不紧急。

## 部署到 GitHub Pages
1. 新建仓库，把 `index.html` 放到根目录并推送。
2. 仓库 Settings → Pages → Source 选 `main` 分支 / root，保存。
3. 访问 `https://<用户名>.github.io/<仓库名>/`（注意结尾斜杠，这就是重定向 URI）。

任何静态托管（Netlify、Cloudflare Pages、本地 `python3 -m http.server`→`http://localhost:8000/`）同理，必须用 http(s) 打开，不能用 `file://`。

## 注册 Azure 应用
1. portal.azure.com → Microsoft Entra ID → 应用注册 → 新注册。
2. 帐户类型：仅限个人 Microsoft 帐户（或“任何组织目录 + 个人帐户”，此时把 `AUTHORITY_TENANT` 改为 `common`）。
3. 重定向 URI：平台选“单页应用程序 (SPA)”，填页面完整地址。
4. API 权限：Microsoft Graph → 委托的权限 → `Tasks.ReadWrite`、`User.Read`。
5. 复制“应用程序(客户端) ID”：可写进文件顶部 `CLIENT_ID`，或打开页面后粘贴，或访问 `页面地址?clientId=你的ID`（保存在浏览器 localStorage）。

## 说明
- 跨象限移动 = 在目标列表新建副本 + 删除原任务（Graph 不支持跨列表移动），因此任务 ID、创建时间、附件、清单步骤（checklist）不会保留。
- 每 每天及窗口获得焦点时自动刷新。
