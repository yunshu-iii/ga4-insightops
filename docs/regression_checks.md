# InsightOps 回归检查

## 固定入口

在项目根目录执行：

```bash
make format      # 自动格式化 Python 源码与测试
make lint        # 格式检查、Python 编译、Ruff 静态检查
make test        # lint + 全部 pytest 单元与 Golden Question 测试
make regression  # 只读数据库/交付物对账，写入回归收据
make regression-full  # 只读对账完整 92 天 GA4 批次与独立报告
make check       # test + regression
make ci          # 与 GitHub Actions 相同的干净源码检查
make benchmark   # 只读本机 MySQL 性能基线
make clean-bootstrap  # 隔离 MySQL 从零 DDL 初始化验证并自动清理
```

`make regression` 不重跑导入、质量门禁、Mart 或异常检测，不修改业务表；它只读取现有审计事实，并将结果写到 `artifacts/regression/latest.json`。
`make regression-full` 同样只读，专门绑定完整 JSON 批次，并写入 `artifacts/regression/full_ga4_latest.json`；它不应被放进无数据的 CI。

## 当前断言

| 范围 | 稳定断言 | 目的 |
| --- | --- | --- |
| 代码契约 | Ruff、编译、pytest、SQLAlchemy URL 隐私契约 | 阻止语法、导入、Pydantic/守护逻辑与连接参数回归 |
| 异常守护 | 零 MAD 的方向性规则；低覆盖只抑制订单键依赖指标；覆盖率指标不作业务解释 | 阻止虚假异常与错误业务解释 |
| 真实 GA4 | `ga4_event_stg` 为 640,055 行；v2 日指标为 14 天；异常运行 `e9975d26-b3c2-4702-b857-622b6c7da4c1` 为 20 个统计异常、0 个可解释异常、20 个抑制异常、112 条总结果 | 防止真实开发样例或守护状态被静默覆盖 |
| 合成场景 | 每个种子运行均为 `synthetic_case=true`；业务可解释为 2/2/8，低覆盖为 2/0/0，历史不足为 0/0/0（统计异常/可解释异常/贡献） | 验证允许、抑制和历史不足三条安全路径 |
| 报告交付 | 两份 artifact 为 `ready`，均有来源绑定、1 个原生图表、1 个审计表、2 个指标卡，且无悬挂 block 引用 | 防止报告失去证据链或误交付半成品 |
| 完整 GA4 | Raw/Staging 均为 4,295,584 行；92 日指标为 5,692 / 4,786 / 4,451（购买 / 有效交易号购买 / 规范订单）；异常为 71 / 24 / 47 / 736，贡献为 15 | 防止完整批次、守护结果或其独立报告被静默替换 |

## 最近通过收据

2026-08-23 的 `make regression` 已通过，收据位于 `artifacts/regression/latest.json`。该收据记录检查时间、真实批次状态、合成场景结果和报告结构计数；不包含密码或原始事件行。

2026-08-24 的 `make regression-full` 已通过，收据位于 `artifacts/regression/full_ga4_latest.json`。它记录完整批次的接入、Raw/Staging、质量门禁、日指标、异常和报告结构对账；不包含密码或原始事件行。

## 有意未覆盖的范围

- 不在每次回归中重跑 64 万行 GA4、54 万行 UCI 的全量导入与所有 Notebook；这些昂贵操作保留给数据重载、口径调整或发布前专项验证。
- 不把公开 GA4 轻量样例的订单/收入结论升级为业务结论；覆盖率守护本身是必须保留的断言。
- 报告 HTML 的结构、语义回退、完整 92 天报告的浏览器图表/来源交互与 390px 窄屏布局均已验证；外网托管与跨浏览器矩阵仍不在本地回归范围内，详见 `docs/reporting.md`。
- CI 已覆盖干净源码检出的格式、编译与 pytest；它不连接数据库，避免将本地数据或生成物误当成 CI 前置条件。
