# InsightOps 工程化交付

## CI

`.github/workflows/quality.yml` 会在推送和 Pull Request 上使用 Python 3.11，安装
`requirements.txt` 后执行 `make test`。该检查刻意不依赖 Docker、数据库、`.env`、本地
数据或已生成报告，因此新检出的代码仓库可以独立验证源码、格式、编译和 11 项测试。

本地可使用：

```bash
make ci
```

`make regression` 仍是本地环境专用：它读取已审计的 MySQL 事实和已生成报告，以确认真实
批次、合成场景和交付物没有漂移。

## 性能基线

```bash
make benchmark
```

该命令只读现有 MySQL 表，重复五次并将中位数、最小值、最大值和样本写入
`artifacts/performance/latest.json`。性能绝对值受机器、Docker 资源、缓存与并发影响；只应
与同一环境的后续运行比较，不能当作生产 SLA。

2026-08-23 的本机基线：

| 查询 | 返回行数 | 中位延迟 |
| --- | ---: | ---: |
| GA4 purchase 覆盖率日聚合（640,055 行事件） | 14 | 959.097 ms |
| 已构建 GA4 日指标读取 | 14 | 0.985 ms |
| 已构建异常结果读取 | 112 | 2.272 ms |

## 干净 Docker 初始化

```bash
make clean-bootstrap
```

该验证通过 `compose.clean.yml` 启动隔离实例：容器名
`insightops-clean-bootstrap-mysql`、端口 `3307`、专用命名卷
`insightops-clean-bootstrap-mysql-data`。脚本检查初始化后恰有四个 InsightOps schema，且至少
十张业务表，随后在退出时删除上述临时容器、网络和专用数据卷。它不会修改正在使用的
`insightops-mysql` 或其 `mysql_data` 卷。

首次验证曾因 Compose 对端口列表的合并语义保留了基础配置的 `3306:3306`，与主库冲突；现已改为
在脚本中显式导出基础编排使用的 `MYSQL_PORT=3307`。修正后验证通过：4 个 schema、20 张表。

## 已完成的连接层治理

`src/db_connection.py` 将 pandas 的只读 MySQL 查询统一到参数化 SQLAlchemy Engine，使用
`mysql+pymysql`、UTF-8 与连接存活检查；连接 URL 的单元测试验证密码不会以明文渲染。日指标与
异常检测的写入仍保留显式 PyMySQL 事务，避免为消除警告而改变事务边界或 SQL 占位符语义。完整
92 天 GA4 批次已用此路径实际回归，并保持固定基线不变。

## 已知后续优化

- GitHub Actions 工作流已准备，但尚未有本地提交、远端仓库或首次云端运行；待用户注册账号并明确授权后再执行，不能把本地 `make test` 表述为云端 CI 已通过。
- 本地报告已完成桌面与 390px 窄屏 QA；外网托管、跨浏览器矩阵、无障碍人工验收与多人/RBAC 仍属于部署前的后续能力。
