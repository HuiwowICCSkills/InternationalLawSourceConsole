# 国际法检索来源控制台

本目录是独立控制台，不包含来源 ID、名称或说明，也不绑定任何检索工具。

## 启动

```powershell
.\start-console.cmd "D:\path\to\source-catalog.json"
```

本地开发时若省略参数，会读取同级目录的 `..\source-catalog.json`。
控制台通过 `server.py --catalog` 或环境变量 `INTL_LAW_SOURCE_CATALOG` 接收来源目录。

控制台只负责：

- 读取外部来源目录；
- 保存每个来源的启用状态与检索备注；
- 校验状态文件中不存在目录之外的来源 ID。

来源目录的维护属于国际法检索工具，不属于本控制台。

来源目录的 `local-skills` 分组可能包含 `multi-search-engine`、`web-access`、`agent-browser`、`spider-mind` 等通用联网/浏览器技能；这些技能不由本控制台安装或发布，需从各自上游单独获取。
