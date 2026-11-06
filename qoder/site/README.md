# Qoder Sites 发布说明

## 1. 本地预览

```powershell
cd qoder\site
..\.venv\Scripts\python.exe -m http.server 8890
# 打开 http://127.0.0.1:8890
```

网站是纯静态文件，无构建步骤。`index.html` 使用相对路径；直接双击 `index.html` 也能打开，但建议用 HTTP 服务预览。

## 2. 发布前替换链接

如果实际代码仓库不是 `xzhtry/powercontext` 的 `qoder/` 目录，请全局替换 `index.html` 中的：

```
https://github.com/xzhtry/powercontext/tree/2026-competition-ecosystem/qoder
https://github.com/xzhtry/powercontext/blob/2026-competition-ecosystem/qoder/...
```

## 3. 用 Qoder Sites 发布

1. 在 Qoder 中打开 `qoder/site` 目录；
2. 选择 Sites / 发布静态站点；
3. 可见范围设为「任何人都可访问」（企业版账号无法公开，请用个人账号）；
4. 发布后复制完整 URL；
5. 用浏览器无痕窗口打开，确认：
   - 首页、5 张截图、技术代码块、验证数据、运行命令都可见；
   - 所有链接可点，没有 404；
   - 390px 宽度不横向溢出；
6. 把 URL 填进 `docs/qoder-development-log.md` 和 `docs/submission-checklist.md`。

> 修改网站后必须再次点击「发布」才会更新线上版本；只保存草稿不会更新。

## 4. 截图来源

`assets/*.webp` 是应用真实运行截图（2026-11-05，本机 Windows 11 + seekdb 1.4.0 + PowerContext 1.4.1）：

| 文件 | 页面 |
| --- | --- |
| `today.webp` | 今日研究台 |
| `hero.webp` | 首屏截图（今日研究台顶部） |
| `library.webp` | 文献库 + SQL 轨迹 |
| `evidence.webp` | 证据表 |
| `synthesis.webp` | 综述台 |
| `memory.webp` | 研究记忆 |

重新截图后替换同名文件即可；建议宽度 1440px、WebP quality 82，保持页面加载速度。

## 5. 不要在网站上放

- API Key、密码、真实个人信息；
- 未发生的用户数量/提效数据；
- 未经授权的论文 PDF 或大段原文；
- 与 Qoder 账号 UID 不一致的站点归属说明。
