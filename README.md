# ZhiShao RDK X5 Project

这是为 ZhiShao / RDK X5 项目准备的 Codex 工作区。

## 当前目标

先完成 Windows 侧项目归档，等待 RDK X5 在身边后，再导入开发板上的 `/home/sunrise/ZhiShao_V2`，随后进行项目合并、优化和同步。

## 目录说明

```text
_import_windows/  Windows 侧已有文件导入区
_import_rdk/      后续从 RDK X5 拉取的项目文件导入区
docs/             项目说明、分析记录、同步流程
scripts/          后续放同步、部署、验证脚本
templates/        可复用模板
work/             临时分析和草稿
outputs/          用户交付物
```

## 已导入 Windows 文件

```text
_import_windows/vlm_service_cascade.py
```

来源：

```text
F:\codex_project\ZhiShao\vlm_service_cascade.py
```

## 待补齐 RDK 文件

开发板在身边后，从 RDK X5 拉取：

```text
/home/sunrise/ZhiShao_V2
```

目标导入到：

```text
_import_rdk/
```

## 推荐工作流程

1. 当前阶段：只做 Windows 侧归档和结构准备。
2. RDK 在身边后：拉取 `/home/sunrise/ZhiShao_V2` 到 `_import_rdk/`。
3. Codex 分析 `_import_windows/` 与 `_import_rdk/` 的差异。
4. 整理统一项目结构。
5. Git 提交合并结果。
6. Codex 再做低风险优化。
7. 同步到 RDK 测试目录验证。
8. 验证通过后再替换 RDK 正式目录。
