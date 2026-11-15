# 四象限待办（Microsoft To Do）

单文件 `index.html`，无需构建。通过 Microsoft Graph 读写你的 To Do，自动创建四个列表：重要紧急、重要不紧急、紧急不重要、不重要不紧急。

打开或刷新看板时：
- 未完成任务按截止日期升序排列（无截止日期的排在后面）
- 距离截止日期不足 5 天（含今天与已过期；例如今天 15 号，19 号及之前会转，20 号暂不转）的事项，会从「重要不紧急」转入「重要紧急」，从「不重要不紧急」转入「紧急不重要」
- 默认的「任务」列表不会改动

云端定时（GitHub Actions）每天 7:00（北京时间）做同样的转入，不依赖哪台电脑开着。

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
6. 若要启用云端定时：同一应用 → Authentication → 打开 “Allow public client flows”；再添加平台 “Mobile and desktop applications”，重定向 URI 填 `http://localhost`。

## 云端定时（GitHub Actions）
1. 按上面第 6 步打开公共客户端。
2. 在已登录 `gh` 的环境运行：`python3 scripts/login_refresh_token.py`。按提示用微软账户完成一次设备代码登录。脚本会把刷新令牌写入仓库的 Actions 密钥 `MS_REFRESH_TOKEN`，不会把令牌打印出来。
3. （可选）把同一个应用的客户端 ID 存为密钥 `AZURE_CLIENT_ID`；不设则使用页面里已有的 ID。
4. 合并到 `main` 后，可在 Actions 里手动跑一次 “Promote due-soon tasks” 做验证。之后每天 7:00（北京时间）自动跑。若运行失败并提示 `invalid_grant`，重新执行第 2 步即可。

## 说明
- 跨象限移动 = 在目标列表新建副本 + 删除原任务（Graph 不支持跨列表移动）。任务 ID、创建时间、附件不会保留；移动时会尽量复制清单步骤和链接资源。
- 官方 To Do 应用的列表排序无法通过接口设置；看板已按截止日期排序。若要在 To Do 里看到同样顺序，请在该列表选择按截止日期排序。
- 页面会在打开时刷新；另有每天一次的自动刷新。
