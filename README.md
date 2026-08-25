# InsightOps

InsightOps 是一个本地可复跑的 AI 增长智能洞察平台。它把公开电商数据接入、质量校验、漏斗建模、异常检测、贡献归因与受限 AI 洞察串成一条可审计工作流。

项目范围和完成标准见 [项目范围基线](docs/project_scope.md)；本地 MVP 的最终交接、架构图、边界与外部发布待办见 [最终交接清单](docs/final_handoff.md)。

## 当前阶段

本地 MVP 已完成公开数据接入、Raw/Staging/Mart、质量门禁、漏斗、客户价值、异常检测守护、受限 Insight Agent、人工复核、合成 Golden Questions、报告、回归入口、CI 工作流、性能基线、干净 Docker 初始化和浏览器 QA。GitHub 远端发布与首次云端 CI 仍需用户注册账号后明确授权。

## 本地前置条件

- Docker Desktop（已启动）
- Python 3.11
- Git

## 首次启动

```bash
cp .env.example .env
# 编辑 .env，替换 MYSQL_ROOT_PASSWORD
docker compose up -d
docker compose ps
```

首次创建 MySQL 数据卷时，容器会执行 `sql/ddl/01_databases.sql`，建立：

- `insightops_raw`：不可变原始数据层
- `insightops_dw`：清洗、事实与指标层
- `insightops_ops`：批次、质量、异常与 Agent 审计层

## Python 环境

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 目录说明

```text
config/       MySQL 与后续 YAML 配置
sql/ddl/      数据库初始化与后续迁移脚本
src/          Python 应用代码
tests/        单元、集成和 Golden Question 测试
data/         本地原始、暂存和合成数据（不提交 Git）
artifacts/    报告、运行 trace 与样例输出（不提交 Git）
docs/         架构、数据字典、操作说明和演示脚本
prompts/      版本化的 Agent 与报告提示词
```

## 回归检查

```bash
make test        # Ruff、编译、单元与 Golden Question 测试
make regression  # 只读核对真实批次、合成批次和报告证据
make check       # 依次执行以上两项，并写入 artifacts/regression/latest.json
make regression-full  # 完整 92 天 GA4 批次与独立报告的只读回归
make ci          # 仅执行可在干净源码检出环境运行的代码检查
make benchmark   # 记录本机只读 MySQL 查询性能基线
make clean-bootstrap  # 隔离 MySQL 从零初始化验证，结束后自动清理临时资源
```

回归检查的范围、断言和当前边界将在 [回归检查说明](docs/regression_checks.md) 中维护。项目当前状态见 [状态检查点](docs/project_state.md)。
工程化交付的运行边界见 [工程化交付说明](docs/engineering_delivery.md)。
