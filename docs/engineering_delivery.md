# InsightOps 工程化交付

## CI

`.github/workflows/quality.yml` 会在推送和 Pull Request 上分别使用 Python 3.11 和 3.14，
按哈希安装 `requirements.lock` 后执行 `make test` 与锁定依赖的安全扫描。该检查不依赖
Docker、数据库、`.env`、本地数据或已生成报告，可独立验证源码、格式、编译和 23 项测试。

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

该验证独立使用 `compose.clean.yml`，每次生成不同的项目名、随机密码和项目专用卷，
不读取真实 `.env`，不发布主机端口。脚本等待认证 SQL 查询成功后检查四个 InsightOps
schema 和至少十张业务表，退出时只清理该次临时资源。它不会修改正在使用的
`insightops-mysql` 或其 `mysql_data` 卷。运行需要 Docker、Bash 和 OpenSSL。

2026-11-05 的安全修复取消了旧的 3307 端口映射和固定测试密码，并验证从零建立
4 个 schema、17 张表后自动清理。历史验证中额外迁移后的表数见阶段记录，不等同于
当前全新数据卷的 DDL 初始化结果。

## 已完成的连接层治理

`src/db_connection.py` 将 pandas 的只读 MySQL 查询统一到参数化 SQLAlchemy Engine，使用
`mysql+pymysql`、UTF-8 与连接存活检查；连接 URL 的单元测试验证密码不会以明文渲染。日指标与
异常检测的写入仍保留显式 PyMySQL 事务，避免为消除警告而改变事务边界或 SQL 占位符语义。完整
92 天 GA4 批次已用此路径实际回归，并保持固定基线不变。

## 已知后续优化

- GitHub Actions 初版因未创建 `.venv` 而失败，此问题已修复；当前先创建 `.venv`、按哈希安装 `requirements.lock` 后运行代码检查及依赖安全扫描。云端不访问本地数据库、数据、报告或 `.env`。
- 本地报告已完成桌面与 390px 窄屏 QA；外网托管、跨浏览器矩阵、无障碍人工验收与多人/RBAC 仍属于部署前的后续能力。
