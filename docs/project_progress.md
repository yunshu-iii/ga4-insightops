# InsightOps 项目进度总结

> 本文按完成顺序记录每一步的目标、实际交付、问题、解决方式与可核验的证据。每完成一个项目步骤，必须在此新增一节；不能用口头状态替代记录。

## 步骤 0：项目基础环境

### 原定目标

建立独立项目目录，固定 Python 3.11 与 MySQL 8.4 的本地可复跑环境。

### 实际完成

- 创建项目目录与本地 Git 仓库（本机绝对路径不提交）。
- 创建 Docker Compose、MySQL 初始化 SQL、`.env` 模板、Python 依赖清单与基础目录结构。
- 使用 Python 3.11 创建项目虚拟环境；MySQL 8.4 Docker 容器已启动并验证三个 schema：Raw、DW、Ops。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| Docker 初始安装/下载过程不稳定 | 用户完成 Docker Desktop 安装并启动后，再使用 Compose 启动和验证容器 |
| 系统保留 Python 3.9 | 不删除系统 Python；项目虚拟环境固定使用 Python 3.11，避免影响其他程序 |

### 证据

- `compose.yaml`
- `sql/ddl/01_databases.sql`
- `docs/project_scope.md`

## 步骤 1：公开数据源获取与初步画像

### 原定目标

获取 UCI Online Retail 与 GA4 Google Merchandise Store 公开样例，确认可用范围与数据限制。

### 实际完成

- 下载 UCI 官方 XLSX，并完成行数、空值、取消单与金额等初步 EDA。
- 在 BigQuery 验证 GA4 公开样例：4,295,584 个事件、270,154 名匿名用户、92 天，覆盖 2020-11-01 至 2021-01-31。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 公开样例可能被误解为真实业务生产数据 | 在数据访问文档中标注匿名化、占位值与“仅技术验证”限制 |
| GA4 查询中使用了样例不存在的 `collected_traffic_source` 字段 | 改为样例可用的 `traffic_source` 首次获得字段，并更正字段语义 |

### 证据

- `docs/data_access.md`
- `docs/eda_uci.md`
- `docs/eda_ga4.md`
- `sql/bigquery/01_profile_ga4.sql`

## 步骤 2：GA4 开发样本导出与文件验证

### 原定目标

导出连续 14 天 GA4 事件样本到本地，作为 MySQL 接入输入。

### 实际完成

- 导出并验证 640,055 条、12 字段、2020-11-01 至 2020-11-14 的事件级 CSV。
- 重命名为 `data/inbound/ga4/ga4_ecommerce_events_20201101_20201114.csv` 并登记 SHA-256。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| BigQuery 本地下载 CSV 上限 10 MB | 改用 Google Drive 导出 |
| Google Drive 单文件结果过大 | 移除未展开的 `event_params` 与 `items` JSON，保留事件分析 MVP 所需字段 |
| Cloud Storage 分片导出需要启用结算账号 | 不为了当前开发样本启用结算；将完整嵌套字段补取定义为后续高优先级方案 |

### 证据

- `sql/bigquery/03_extract_ga4_events_drive.sql`
- `docs/ga4_ingestion_strategy.md`
- `data/inbound/ga4/ga4_ecommerce_events_20201101_20201114.csv`（本地忽略文件）

## 步骤 3：GA4 Raw 接入

### 原定目标

以不可覆盖的批次方式将验证过的 GA4 CSV 导入 MySQL Raw 层，并保留来源追溯信息。

### 实际完成

- 建立 `ingestion_batch` 与 `ga4_event_raw` 表。
- 导入批次 `9a2d8d7c-0f5b-4c57-a54d-98c59b9c5a27`，写入 640,055 行。
- 核对数据库行数、日期范围、购买事件数与收入汇总均和 CSV 一致。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 已存在的 MySQL 容器不会自动执行新增初始化 SQL | 明确手动执行新增 DDL；后续新环境仍会在首次启动时自动执行 |
| Raw 层需要可重复且不可覆盖 | 以 `batch_id`、文件 SHA-256 和源文件行号实现追加式追溯 |

### 证据

- `sql/ddl/02_raw_tables.sql`
- `src/ingest_ga4_raw.py`
- `docs/data_access.md`

## 步骤 4：GA4 质量门禁与事件 Staging

### 原定目标

建立可阻断下游的质量规则、拒绝记录和事件 Staging 清洗层。

### 实际完成

- 建立 11 条 BLOCKER 与 3 条 WARNING 规则、质量运行/结果/拒绝记录审计表。
- 质量运行 `3d6ec6a4-6192-4707-81d2-0c12b3c1d1e9` 通过：11 条 BLOCKER 全部通过。
- 将 640,055 条事件写入 `ga4_event_stg`，并派生 `page_path`、`is_purchase` 与 `is_order_eligible`。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 初版将 purchase 缺交易号视为全局 BLOCKER，导致门禁阻断 | 将规则拆分：缺收入仍为 BLOCKER；缺交易号降为订单层 WARNING，因为事件本身仍可用于漏斗分析 |
| 437 个购买事件关联 2 个重复交易号 | 事件 Staging 保留事实；订单事实层将按交易号选取一条规范记录，禁止直接累计原始 purchase 行 |
| 23 个 purchase 缺交易号 | 保留事件与收入；订单事实/RFM/LTV 层排除并记录原因 |

### 证据

- `docs/ga4_data_quality.md`
- `docs/ga4_quality_report.md`
- `sql/ddl/03_quality_tables.sql`
- `sql/ddl/04_staging_tables.sql`
- `src/run_ga4_quality.py`
- `src/stage_ga4_events.py`

## 下一步

接入 UCI Online Retail 的 Raw 数据，执行其质量门禁并建立交易 Staging；完成后新增“步骤 7”总结。

## 步骤 5：Jupyter 执行验证与项目治理固化

### 原定目标

安装 Jupyter 执行组件，顶到底执行此前未执行的 GA4 质量 notebook；建立持续维护的步骤总结与执行规则文档。

### 实际完成

- 将 `nbformat`、`nbclient`、`ipykernel`、`nbconvert` 写入依赖并安装到项目 Python 3.11 环境。
- 注册 `InsightOps (Python 3.11)` 内核，并顶到底执行质量 notebook。
- 实际输出确认 640,055 行、14 天范围、11 条 BLOCKER 全通过及 2 条 WARNING。
- 建立本进度总结和 `docs/execution_rules.md`，固化依赖处理、降级记录、状态检查点与复跑要求。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 缺少 notebook 执行组件 | 将组件纳入项目依赖后安装并注册专用内核 |
| 初始 notebook 缺少 cell ID 提示 | nbconvert 自动补齐；nbformat 复核确认 notebook 合法且每个单元格均有 ID |

### 证据

- `requirements.txt`
- `notebooks/01_ga4_raw_quality.ipynb`
- `docs/execution_rules.md`

## 步骤 7：UCI Raw 接入、质量门禁与交易 Staging

### 原定目标

以可追溯批次接入 UCI Online Retail 官方 XLSX，复用质量门禁模式，并建立不删除原始记录的交易明细 Staging。

### 实际完成

- 建立 `uci_retail_line_raw` 与 `uci_retail_line_stg`，并以批次、源文件行号和 SHA-256 保证可审计追溯。
- 导入批次 `7aa2b0f4-12aa-4dfb-890c-ffadc8f9d6fa`，写入 541,909 行；日期范围为 2010-12-01 至 2011-12-09。
- 执行 `uci_retail_raw_v1`：5 条 BLOCKER 全部通过，6 条 WARNING 被记录而非删除。
- 写入 541,909 条 Staging 明细；派生取消、完全重复、有效销售、客户可识别与行收入字段，其中 524,878 行标记为有效销售行。
- 新增并校验 UCI 的可复现质量 Notebook。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| Docker Desktop 在执行前未运行 | 启动 Docker Desktop，确认守护进程就绪后再执行 DDL 和导入 |
| PyMySQL 将 SQL 的 `LIKE 'C%'` 视为字符串格式化占位符 | 改为 `LIKE 'C%%'`；保留一次 `FAILED` 质量运行作工程审计，并用新的运行 ID 成功复跑 |
| 原始数据包含取消、负数量、零价和重复明细 | Raw 层完整保留；Staging 添加显式标识，后续销售指标只取 `is_valid_sale_line = 1` |

### 证据

- `sql/ddl/05_uci_tables.sql`
- `src/ingest_uci_raw.py`
- `src/run_uci_quality.py`
- `src/stage_uci_retail_lines.py`
- `docs/uci_data_quality.md`
- `docs/uci_quality_report.md`
- `notebooks/02_uci_raw_quality.ipynb`

## 步骤 8：规范订单事实表与指标口径

### 原定目标

从通过质量门禁的 UCI 与 GA4 Staging 构建版本化订单事实，明确去重、排除和货币边界，并把核心指标写成可审计口径。

### 实际完成

- 建立 `insightops_mart`、UCI/GA4 订单事实表、转换运行表及事实构建审计表。
- UCI 仅聚合有效销售行，形成 19,960 个订单，GMV 为 £10,642,110.80，平均订单金额为 £533.17；4,338 名可识别客户覆盖 18,532 个订单。
- GA4 从 625 个事件层合格购买事件中排除 435 条 `(not set)` 占位交易号事件，并对剩余交易号去重，形成 189 个规范订单、$12,836.00 收入和 170 名匿名购买用户。
- 所有事实行保存来源批次、质量运行、构建运行与定义版本；构建运行 `cfd9f615-d65a-4113-a8d4-c0bbe2e1317f` 成功写入 20,149 行。
- 建立指标字典与可复现订单事实审计 Notebook。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| GA4 的 `is_order_eligible = 1` 中仍有 435 条 `(not set)` 占位交易号 | 将其明确排除在订单事实外，仅保留在事件/漏斗分析中；把排除量写入事实构建审计表 |
| 同一 GA4 交易号可能有多个购买事件 | 订单事实按交易号保留 `event_ts, stg_event_id` 最早的一条，并保留原始事件数 |
| UCI 为 GBP、GA4 为 USD，且非同一业务样本 | 指标字典与 Notebook 强制分源展示，禁止相加或表述为统一业务总额 |

### 证据

- `sql/ddl/06_order_facts.sql`
- `src/build_order_facts.py`
- `docs/metric_dictionary.md`
- `notebooks/03_order_facts_audit.ipynb`

### 自检与测试（补充）

- `build_order_facts.py` 已完成 Python 编译、Ruff 格式与静态检查。
- 实际构建运行状态为 `SUCCEEDED`，写入 20,149 条事实；数据库核验了 UCI/GA4 订单数、金额、购买用户数、GA4 重复交易号处理及占位交易号零泄漏。
- 审计 Notebook 已顶到底执行且无错误。自动化单元测试将在后续测试专门步骤补充；本次为真实数据库集成核验。

## 步骤 9：GA4 会话与结账漏斗事实

### 原定目标

将通过质量门禁的 GA4 事件汇总到会话粒度，建立可审计的日漏斗指标，并定义不受占位交易号或稀疏事件误导的转化口径。

### 实际完成

- 建立 `ga4_session_fact` 与 `ga4_daily_funnel_metric`，以 `user_pseudo_id + ga_session_id` 为会话键；构建运行 `b6b845e1-0da3-4d90-97be-233d199790a5` 写入 47,911 个会话和 14 条日指标。
- 确认 `add_to_cart` 仅有 4 个事件、1 个会话，未将其作为正式主漏斗阶段。
- 固定主漏斗为“开始结账 → 同会话购买事件 → 同会话规范订单”：1,911 个结账会话、578 个购买事件会话（30.25%）和 176 个规范订单会话（9.21%）。
- 新增日粒度指标、指标字典条目和可复现漏斗审计 Notebook。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 标准四步电商漏斗的 `add_to_cart` 极度稀疏，且无法与其余步骤构成可靠链路 | 依据真实事件覆盖改为结账完成漏斗；将加购数据保留为覆盖守护项和明确限制 |
| 初版比率自检直接比较数据库除法结果，受 MySQL 默认显示精度影响 | 构建 SQL 与自检均改为显式高精度计算后 `ROUND(..., 8)`，使口径与存储精度一致 |
| 购买事件与规范订单间存在明显差异 | 同时报出事件级购买和排除占位交易号后的规范订单转化率，禁止将两者混用 |

### 自检与测试

- 新脚本通过 Python 编译、Ruff 格式和静态检查。
- 真实构建运行状态为 `SUCCEEDED`；会话事实总数与 14 条日指标汇总完全一致（47,911）。
- 漏斗阶段顺序自检中，“购买无结账”“规范订单缺必要阶段”“规范订单无购买”均为 0。
- 日转化率按 8 位精度重算，14 天中的不一致数为 0；审计 Notebook 顶到底执行无错误。
- 未覆盖边界：GA4 公开样例只有 14 天轻量事件载荷，不能据此推断真实业务转化或完整商品漏斗；后续若补取完整 `items`/参数载荷，应重新评估漏斗定义。

### 证据

- `sql/ddl/07_ga4_session_funnel.sql`
- `src/build_ga4_session_funnel.py`
- `docs/metric_dictionary.md`
- `notebooks/04_ga4_session_funnel_audit.ipynb`

## 步骤 10：UCI 客户价值 Mart

### 原定目标

从 UCI 有效订单构建仅覆盖可识别客户的客户聚合、RFM 分层和可解释历史价值代理，并明确覆盖率与非预测边界。

### 实际完成

- 建立 `uci_customer_value_fact` 和 `uci_customer_value_summary`，快照日固定为 2011-12-10。
- 为 4,338 名可识别客户生成 Recency、Frequency、Monetary、规则分群和累计消费代理；2,845 名客户有复购。
- 客户分析覆盖 18,532 个有效订单（92.845691%）及 £8,887,208.89 历史消费；8 名多国家客户显式标记为 `MULTIPLE`。
- 将累计消费明确命名为历史价值代理，而不描述为未来 LTV 预测。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 初版汇总 SQL 把客户数 4,338 错写为有客户 ID 的订单数 | 自检发现后，将汇总改为从订单事实直接计算 18,532 个可识别订单；幂等重跑仅更新派生汇总并保留原运行审计 |
| RFM 传统 `NTILE` 会在并列订单频次/金额处任意拆分客户 | 使用 `CUME_DIST` 五分位，使相同数值获得相同分数 |
| 少量客户跨多个国家 | 8 名客户标记为 `MULTIPLE`，避免静默选择单一国家 |

### 自检与测试

- 构建脚本通过 Python 编译、Ruff 格式和静态检查。
- 修正后构建运行 `5ad2c2ef-2368-4436-8041-607c908ab10e` 为 `SUCCEEDED`；事实表未重复写入，派生汇总已更新。
- 订单覆盖与订单事实对账无差异；客户数和历史消费与客户事实对账无差异。
- 4,338 名客户的 R/F/M 分数全部位于 1–5，分群缺失数为 0；多国家客户数为 8，已按规则标记。
- 未覆盖边界：这是单个公开样例的历史观察窗；尚未训练未来价值、流失概率或因果模型。

### 证据

- `sql/ddl/08_uci_customer_value.sql`
- `src/build_uci_customer_value.py`
- `docs/uci_customer_value.md`

## 步骤 11：GA4 日指标、异常检测与贡献归因

### 原定目标

从已验证的 GA4 会话漏斗和规范订单事实构建日粒度指标；用仅向后的 rolling median + MAD 发现统计异常；按设备和首次获客渠道描述订单/收入差值构成，并建立可复跑审计材料。

### 实际完成

- 新建 `ga4_daily_metric`、`ga4_daily_dimension_metric`、`metric_anomaly_result` 和 `metric_anomaly_contribution` 四张表。
- 日指标构建运行 `51987594-ceb4-423d-a277-188d1d6d40ab` 成功写入 14 条日指标与 169 条维度日指标（183 行）。
- 异常检测运行 `71a6d517-8df8-454e-87a6-35c7e5181046` 成功写入 84 条日期×指标检测结果与 104 条贡献记录（188 行）。
- 对六项日指标使用此前最多 7 天、至少 5 个历史点、中位数/MAD 与稳健 Z 阈值 3.5；MAD 为零时以方向性异常标记而不写入虚假的无限 Z 分数。
- 生成业务读者报告 `docs/ga4_anomaly_report.md` 和可执行审计 Notebook `notebooks/06_ga4_anomaly_audit.ipynb`。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 初版日指标读取时误用了不存在的 `session_date` 列 | 改为会话漏斗日表实际的 `metric_date` 列后重新运行，成功写入 Mart |
| 公开样例的前 10 天规范订单为零，MAD 也为零 | 将零 MAD 规则显式实现为“同中位数=正常、偏离=方向性异常”，并在报告中标为短观察窗限制 |
| 设备和渠道都是完整切片，若相加会重复解释同一差值 | 报告与指标字典明确把它们列为两套独立描述切片，禁止相加或因果化 |
| Pandas 对直接 PyMySQL 连接给出兼容性警告 | 实际 SQL、写入和所有对账均成功；记录为后续统一迁移 SQLAlchemy 连接层的工程优化项，不影响本步骤数据口径 |
| 初版检测把前 10 天规范订单为零解释为订单指标从零基线出现 | 追加按日 purchase 与交易号覆盖核验：前 10 天有 421 条 purchase，但 398 条为 `(not set)`、23 条缺交易号；将 16 条订单相关结果重新定性为订单标识覆盖异常，并把覆盖率守护项列为下一步 |

### 自检与测试

- 两个新增脚本均通过 Python 编译、Ruff 格式和静态检查。
- 日指标与异常检测真实运行均为 `SUCCEEDED`；日指标 14 行与会话漏斗及规范订单事实逐日对账，不一致数为 0。
- 84 个检测结果的状态分布正确：每项指标 5 条 `INSUFFICIENT_HISTORY`；订单会话、订单、收入和结账至规范订单率各有 4 条 `ANOMALY_HIGH`，观察会话和开始结账会话均无异常。
- 贡献记录没有孤儿异常 ID；11 月 13 日收入中 desktop $3,203（55.70%）、mobile $2,547（44.30%），与当日 $5,750 总差值对账一致；但由于有效交易号覆盖变化，这些构成不能用于业务解释。
- 追加 purchase/交易号覆盖自检：前 10 天 421 条 purchase 中 398 条为 `(not set)`、23 条缺交易号，规范订单键覆盖为 0%；因此 16 条订单相关高异常被重新标记为覆盖异常。
- 审计 Notebook 顶到底执行并校验 14 条日指标、84 条检测结果、16 条高异常和贡献结果；未覆盖边界为短时间序列、交易号覆盖断层和公开轻量样例，不能将当前结果作为生产告警或因果结论。

### 证据

- `sql/ddl/09_daily_metrics_anomalies.sql`
- `src/build_ga4_daily_metrics.py`
- `src/run_ga4_anomaly_detection.py`
- `docs/ga4_anomaly_report.md`
- `notebooks/06_ga4_anomaly_audit.ipynb`

## 步骤 12：交易号覆盖守护与异常解释抑制

### 原定目标

将已发现的交易号覆盖断层落实为数据库字段、日指标、异常检测状态和贡献生成规则；保留数据质量审计线索，但阻止订单、收入及渠道构成被误读为业务异常。

### 实际完成

- 新增可重复迁移 `sql/migrations/001_ga4_transaction_id_coverage_guardrail.sql`；为日指标增加 purchase 事件数、有效交易号 purchase 事件数与覆盖率，为检测结果增加 `is_business_interpretable` 和解释备注。
- `src/build_ga4_daily_metrics.py` 升级为 `ga4_daily_metrics_v2`：运行 `8a9acff4-fa36-4921-b1c0-8d8fe4f2ef9d` 写入 14 条日指标和 169 条日维度指标。
- `src/run_ga4_anomaly_detection.py` 升级为 `ga4_mad_anomaly_v2`：以 95% 有效交易号事件覆盖率检查当前日和此前最多 7 天窗口；运行 `e9975d26-b3c2-4702-b857-622b6c7da4c1` 写入 112 条检测结果，其中 20 条统计异常、70 条不可作业务解释、0 条贡献记录。
- 生成守护记录 `docs/ga4_transaction_id_coverage_guardrail.md`，更新指标字典、异常报告、项目状态与长期执行规则；新增并执行审计 Notebook `notebooks/07_ga4_transaction_coverage_guardrail_audit.ipynb`，并将原有完整异常报告更新为 v2 守护版。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| MySQL 实例不支持 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` | 迁移改为先查 `information_schema.columns`、再动态执行单列 `ALTER TABLE`；已可安全重复执行 |
| 单日 11 月 12 日后覆盖率已接近或达到 100%，但历史仍不可信 | 守护检查当前日加此前最多 7 天；只要窗口内仍有低覆盖日，订单键依赖指标继续不可作业务解释 |
| 初版已有贡献记录容易在后续被误用 | 保留 v1 作为历史审计证据；v2 使用新定义版本并在守护未通过时不生成任何贡献记录 |

### 自检与测试

- 两个更新脚本通过 Python 编译、Ruff 格式与静态检查。
- 迁移、日指标构建和异常检测均真实执行成功；v2 派生层的 purchase 事件 648、有效交易号事件 190，均与 Staging 汇总完全一致。
- 14 个日覆盖率已逐日核验：11 月 1–10 日全部 0%，11 月 11 日 43.75%，11 月 12 日 98.15%，11 月 13–14 日 100%。
- 边界测试通过：56 条规范订单依赖结果中可作业务解释的数量为 0；覆盖率检测结果可作业务解释的数量为 0；v2 贡献记录为 0。
- 迁移已第二次执行以验证幂等性；字段均已存在且未发生结构变化。Notebook 顶到底执行并包含上述断言，执行输出无错误；未覆盖边界为 95% 阈值尚未通过完整生产数据校准，以及 14 天历史不足以形成稳定告警基线。

### 证据

- `sql/migrations/001_ga4_transaction_id_coverage_guardrail.sql`
- `src/build_ga4_daily_metrics.py`
- `src/run_ga4_anomaly_detection.py`
- `docs/ga4_transaction_id_coverage_guardrail.md`
- `notebooks/07_ga4_transaction_coverage_guardrail_audit.ipynb`

## 步骤 13：受限 Insight Agent 与报告证据包

### 原定目标

以固定工具和 Pydantic 契约构建受限 Insight Agent；Agent 只能读取已审计的聚合证据，每条事实结论必须可追溯，并强制尊重交易号覆盖守护。

### 实际完成

- 新建 `src/insight_agent.py`：定义 Evidence Package、Evidence Reference、Finding、Claim 与 Response 的 Pydantic v2 契约；Agent 不调用模型、数据库或任意 SQL，只解释已传入的证据包。
- 新建 `src/build_insight_evidence_package.py`：用固定、参数化 SQL 从 v2 异常运行生成只读 JSON 包；新建 `src/run_insight_agent.py` 生成可保存的结构化回答追踪。
- 实际生成 `artifacts/evidence_packages/ga4_v2_guardrail_evidence.json` 与 `artifacts/run_traces/ga4_v2_guardrail_agent_response.json`。
- 新增 `docs/insight_agent.md`，明确允许范围、禁止范围、追溯字段、可复跑命令和后续 LLM 接入边界。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 公开样例中的统计异常全部受交易号覆盖守护抑制，容易仍被表述为业务增长 | 将 `is_business_interpretable` 设计为输出分流的强制条件：为 false 时只能输出数据质量诊断，不能生成业务结论 |
| 尚未配置可安全使用的 LLM 凭据，也不能让模型取得更多数据权限 | 先实现确定性 MVP，验证证据边界和输出契约；未来模型只能作为同一结构化证据与输出契约的语言适配层 |

### 自检与测试

- `insight_agent.py`、证据包构建器和运行入口通过 Python 编译、Ruff 格式与静态检查。
- pytest 阻断测试 2/2 通过：被抑制证据不会变成业务结论；允许解释的合成证据保留 `query_id` 与 `run_id`，并明确不证明因果。
- 端到端真实运行：证据包为 20 条统计异常、0 条可作业务解释、20 条抑制、0 条贡献；对“这些异常是否代表业务增长？”的回答为 0 条业务结论、1 条含 20 个引用的数据质量诊断，`human_review_required = true`。
- 未覆盖边界：当前是确定性 Agent MVP；尚未接入 LLM、Streamlit 人工复核界面或提示词注入/模型输出的集成测试。

### 证据

- `src/insight_agent.py`
- `src/build_insight_evidence_package.py`
- `src/run_insight_agent.py`
- `tests/test_insight_agent.py`
- `docs/insight_agent.md`
- `artifacts/evidence_packages/ga4_v2_guardrail_evidence.json`
- `artifacts/run_traces/ga4_v2_guardrail_agent_response.json`

## 步骤 14：Streamlit 证据审阅台与人工复核

### 原定目标

把已审计的 Evidence Package、受限 Agent 的结构化回答和人工结论汇集到一个只读审阅界面；禁止任意查询、原始记录展示和自动业务动作。

### 实际完成

- 新建 `src/streamlit_review_app.py`：页面只能从 `artifacts/evidence_packages/` 中选择版本化 JSON 包，展示解释闸门、统计发现、引用链及确定性 Agent 回答。
- 新增 `HumanReviewRecord` Pydantic 契约：本地人工复核记录同时绑定证据包 SHA-256、回答 SHA-256、来源批次和异常运行 ID；`automated_action_taken` 固定为 `false`。
- 人工复核表单允许记录“需要进一步调查 / 确认数据质量问题 / 不采纳”，并强制要求审阅角色与至少 10 个字符的判断依据；记录只写入本地 `artifacts/reviews/`。
- 生成运行与安全说明 `docs/streamlit_review_console.md`。当前 v2 样例的解释闸门正确关闭：20 条统计异常、0 条可作业务解释、20 条被守护抑制、0 条维度贡献。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 页面容易被误当成可直接分析或执行业务动作的控制台 | 固定为证据包选择器；不提供 SQL、原始事件、上传、模型调用或外部动作入口，并在侧栏和复核区显式说明边界 |
| 复核结论若只保存文字，无法核对其对应证据 | 将证据包与回答的 SHA-256、`source_batch_id` 和 `anomaly_run_id` 设为必填、受校验字段 |
| 当前样例所有异常已被数据质量守护抑制 | 以醒目的琥珀色“解释闸门已关闭”阻断业务解释，并仅允许记录数据质量诊断或继续调查 |
| Streamlit 首次运行提示 `use_container_width` 将弃用 | 改为当前 API 的 `width="stretch"`，并重新通过静态检查、编译和测试 |

### 自检与测试

- `insight_agent.py`、`streamlit_review_app.py` 与新增测试通过 Ruff 格式、静态检查及 Python 编译。
- pytest 4/4 通过：既有受限 Agent 的两项阻断测试，以及人工复核记录的追溯/不执行性和最短判断依据边界测试。
- 本地 Streamlit 服务健康检查在参数修复后返回 `ok`；浏览器实测已渲染证据链、受限回答和人工复核三个页面区域，未提交任何人工记录。
- 视觉核验确认解释闸门、统计卡片和人工表单可见；页面仅显示聚合证据与引用，不显示原始事件。
- 未覆盖边界：当前为本地单用户 MVP，尚无登录、RBAC、集中审阅存储、审阅记录防篡改或部署级安全控制；投入多人或外网使用前必须先补齐。

### 证据

- `src/streamlit_review_app.py`
- `src/insight_agent.py`
- `tests/test_human_review.py`
- `docs/streamlit_review_console.md`
- `artifacts/evidence_packages/ga4_v2_guardrail_evidence.json`

## 步骤 15：合成异常与 Golden Questions 端到端测试

### 原定目标

建立明确标记、与真实批次隔离的合成日指标场景，验证真实异常检测、交易号覆盖守护、维度贡献、Evidence Package、受限 Agent 与人工复核前边界能端到端符合预期。

### 实际完成

- 新建 `src/synthetic_ga4_cases.py`，定义三种确定性场景：完整覆盖下的业务可解释订单/收入异常、50% 覆盖下的相同异常抑制，以及只有 4 天历史的历史不足场景。
- 新建 `src/run_synthetic_ga4_anomaly_cases.py`：每次种子运行在 `transformation_run.input_description` 写入 `synthetic_case: true`，再调用真实 `ga4_mad_anomaly_v2`、证据包构建器和受限 Agent，并把 Golden Questions 的期望/实际结果作严格断言。
- 新增 `tests/test_synthetic_anomaly_cases.py`；同时修正证据包限制文字，使其从所选批次的实际交易号覆盖率生成，避免将公开样例的“前十天 0%”错误带入覆盖完整的合成或后续真实批次。
- 三个真实端到端运行均通过：完整覆盖场景为 2 个可解释异常、8 条贡献、2 条业务发现；低覆盖场景为 2 个统计异常、0 个可解释异常、0 条贡献、1 条数据质量诊断；历史不足场景为 0 个统计异常。
- 新增 `docs/golden_questions.md`，保存问题、预期、实际批次/运行 ID、重跑命令与边界。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 若合成数据和真实批次共用来源标识，后续可能误把测试结果当作业务证据 | 对每种场景使用稳定、独立 UUID batch ID，并在种子运行 JSON 明确写入 `synthetic_case: true`；文档禁止其用于真实业务解释 |
| 初版证据包把公开轻量样例的静态覆盖率限制带入任何批次 | 改为查询当前证据包批次的日覆盖率，生成批次特定限制文字 |
| pandas 再次提示 PyMySQL 连接兼容性 | 所有写入、查询和断言实际成功；不在测试步骤混入连接层重构，记录为步骤 18 的工程优化项 |

### 自检与测试

- 新增/修改脚本通过 Ruff 格式、静态检查与 Python 编译；`tests/test_insight_agent.py`、`tests/test_human_review.py`、`tests/test_synthetic_anomaly_cases.py` 合计 7/7 通过。
- 实际运行三个隔离批次；种子审计显示 `synthetic_case=true`，输出行数分别为 40、40、20。
- 独立 MySQL 对账复核：业务可解释 run `28d68188-0b8d-4fc9-aed7-88829c6b33b2` 为 2/2/0（统计异常/可解释/抑制）与 8 条贡献；低覆盖 run `af89c64c-55e9-444e-9752-faf9eac10ed1` 为 2/0/2；历史不足 run `2d91609f-f545-4201-99e7-aac0ba394bb7` 为 0/0/0。
- 真实 GA4 v2 日指标批次仍为 14 行，确认合成测试未覆盖或污染真实派生数据。
- 未覆盖边界：合成测试从派生日指标开始，并不取代 Raw 接入和质量门禁测试；生产阈值、真实异常基线、因果验证、LLM 安全与多人审阅控制仍需后续验证。

### 证据

- `src/synthetic_ga4_cases.py`
- `src/run_synthetic_ga4_anomaly_cases.py`
- `tests/test_synthetic_anomaly_cases.py`
- `docs/golden_questions.md`
- `artifacts/evidence_packages/synthetic/synthetic_ga4_anomaly_manifest.json`

## 步骤 16：正常周报与合成异常报告输出

### 原定目标

以已审计聚合证据为唯一事实来源，形成一份明确“不作业务判断”的公开样例正常周报，以及一份展示守护通过路径的合成异常报告；分别输出 Markdown 与可移植 HTML。

### 实际完成

- 新建 `src/build_report_artifacts.py`，从守护版日指标、异常结果和已保存的合成 manifest 读取聚合数据，输出两份 Markdown 源稿和符合统一 artifact 契约的 `artifact.json`。
- 生成 `artifacts/reports/normal_week/`：14 日公开样例周报显示 20 条统计异常、0 条可作业务解释、648 条购买事件中 190 条有效交易号（29.3%）；用 14 点覆盖率图表说明为何不能作业务归因。
- 生成 `artifacts/reports/synthetic_anomaly/`：用 8 日合成订单序列、2 个可解释异常、8 条贡献和审计表说明检测—贡献—Agent 的守护通过路径；反复标注其不代表真实业务。
- 两份 `artifact.json` 均通过便携式报告打包器的结构、来源、内容与语义回退校验，并生成自包含 `report.html`；新增交付/复跑说明 `docs/reporting.md`。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| MySQL 参数化语句将 `DATE_FORMAT` 中的 `%Y-%m-%d` 误作 Python 格式占位符 | 改为 `%%Y-%%m-%%d`，重新通过静态检查并生成报告 |
| 打包器首次找不到兼容无头 Chromium | 先完成 `structural_only` 验证；发现本机 Google Chrome 后重试增强验证 |
| 本机 Chrome 在静态图表提取阶段超过 43 秒仍超时 | 按打包器规则停止重试，不下载额外浏览器；保留已验证的自包含 HTML 与语义回退，并把增强浏览器 QA 记为未覆盖边界 |

### 自检与测试

- 报告生成器通过 Ruff 格式、静态检查与 Python 编译；实际读取 MySQL 聚合指标和合成 manifest 后成功输出两份源稿和 canonical artifact。
- 每份报告的首次打包均通过 validation、package 与 structural verification：11 个报告块、1 个原生图表、2 个指标卡、1 个审计表，来源元数据与无脚本语义回退均存在。
- 正常周报的日粒度为 14 行，合成报告的日粒度为 8 行、贡献记录为 8 行；生成器对这些行数设有断言，防止报告静默使用不完整输入。
- 未覆盖边界：兼容 Chromium 的增强渲染、窄屏布局和来源交互自动化检查因浏览器超时未完成；HTML 的结构化与语义回退验证已通过，但在对外发布前应在稳定浏览器环境再执行该增强验证。

### 证据

- `src/build_report_artifacts.py`
- `docs/reporting.md`
- `artifacts/reports/normal_week/report.md`
- `artifacts/reports/normal_week/report.html`
- `artifacts/reports/synthetic_anomaly/report.md`
- `artifacts/reports/synthetic_anomaly/report.html`

## 步骤 17：完整回归测试与质量检查入口

### 原定目标

将分散的单元测试、守护逻辑、真实批次数据质量信号、合成 Golden Questions 与报告来源契约收敛为可重复执行的单一入口，并产出机器可读回归收据。

### 实际完成

- 新增 `Makefile`：`make lint`、`make test`、`make regression` 与 `make check` 分别覆盖静态质量、完整 pytest、真实数据只读对账和组合回归。
- 新增 `src/run_project_regression.py`：只读核对 GA4 Staging 640,055 行、真实 v2 日指标 14 天、守护版异常 20/0/20/112、三个合成场景的审计标记与期望结果，以及两份报告的来源/图表/表格契约；生成 `artifacts/regression/latest.json`。
- 新增异常守护与报告 artifact 契约测试，使 pytest 覆盖扩大到 10 项；README 更新为当前阶段与回归命令，新增 `docs/regression_checks.md`。
- 项目范围中的“合成异常跑通报告”和“pytest、质量检查、Golden Questions 可重复运行”完成基线已勾选。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 只跑 pytest 无法发现真实批次被覆盖或报告证据链断开 | 将真实 GA4 行数、守护结果、合成运行标记和 artifact block/source 关系加入只读数据库/文件对账 |
| 把全量导入与 Notebook 全部纳入每次回归会使反馈慢且不必要 | 将高信号稳定断言放入默认回归；全量重跑保留给数据重载、口径变更或发布前专项验证 |
| 报告 HTML 的浏览器增强 QA 尚有环境限制 | 回归继续验证 artifact 来源、结构与语义回退；浏览器超时作为明确未覆盖项，不误报为已完成视觉验证 |
| 首次全仓 `make check` 发现既有 `ingest_ga4_raw.py` 不符合 Ruff 格式 | 运行项目定义的 `make format`，仅调整一处排版；随后完整 `make check` 通过 |

### 自检与测试

- 最终 `make check` 通过：全仓 Ruff 格式/静态检查、Python 编译、完整 pytest 10/10 与只读数据库/报告回归全部成功。
- `make regression` 真实执行并生成 `PASSED` 收据：GA4 Staging 640,055 行、真实日指标 14 天、异常守护为统计 20 / 可解释 0 / 抑制 20 / 总结果 112。
- 三个合成场景再次从数据库审计结果验证：`business_interpretable` 为 2/2/8，`coverage_suppressed` 为 2/0/0，`insufficient_history` 为 0/0/0。
- 两份报告 artifact 均为 `ready`，各有 10 个 manifest block、2 个指标卡、1 个图表和 1 个表，且所有原生证据块具有有效来源引用。
- 未覆盖边界：还未接入 CI、干净环境从零复现、全量数据重载、所有 Notebook 再执行与浏览器增强图表 QA；这些将作为下一工程化步骤的明确任务。

### 证据

- `Makefile`
- `src/run_project_regression.py`
- `tests/test_ga4_anomaly_guardrails.py`
- `tests/test_report_artifact_contracts.py`
- `docs/regression_checks.md`
- `artifacts/regression/latest.json`

## 步骤 18：CI、性能基线与干净环境复现

### 原定目标

让源码质量检查能在无本地数据、无数据库和无生成交付物的环境中执行；为已审计 MySQL 查询留下本机性能基线；并用隔离容器确认 DDL 可从零初始化且不会影响当前开发数据库。

### 实际完成

- 新增 `.github/workflows/quality.yml`：在 push 与 pull request 中使用 Python 3.11 安装 `requirements.txt` 并执行 `make test`。CI 只覆盖源码格式、编译和 pytest，不读取 `.env`、Docker、数据库、数据文件或报告 artifact。
- 将报告 artifact 的测试改为内存 fixture 契约测试，真实报告文件的完整来源/结构核对继续由本地 `make regression` 负责；因此 CI 不再错误依赖开发机生成物。
- 新增 `src/benchmark_project.py` 与 `make benchmark`，对三类只读 MySQL 查询各测量 5 次，写入 `artifacts/performance/latest.json`。当前中位延迟为：64 万行事件日聚合 959.097 ms、日指标读取 0.985 ms、异常结果读取 2.272 ms。
- 新增 `compose.clean.yml`、`scripts/verify_clean_docker_bootstrap.sh` 与 `make clean-bootstrap`；隔离实例使用 3307、独立容器/项目/命名卷，实际从零初始化验证得到 4 个 schema、20 张表，随后自动清理。
- 新增 `docs/engineering_delivery.md`，并更新 README、回归说明、状态检查点与执行规则。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 初版报告契约测试直接读取本机生成的 artifact，GitHub 的干净检出没有这些文件 | 抽出纯字典结构校验函数；pytest 使用最小内存 fixture，真实 artifact 检查留给连接本地证据的 `make regression` |
| 首次隔离 Docker 启动仍绑定 3306，提示端口已被主 MySQL 占用 | Compose 合并端口列表会保留基础配置；删除额外端口覆盖，并在验证脚本中显式导出基础 `compose.yaml` 使用的 `MYSQL_PORT=3307`，重跑成功 |
| pandas 使用 PyMySQL 连接仍有兼容性警告 | 本步骤不为消警告混入查询语义改动；将 SQLAlchemy 连接层迁移作为明确后续工程任务 |

### 自检与测试

- `bash -n scripts/verify_clean_docker_bootstrap.sh` 通过；全仓 Ruff 格式、Python 编译、Ruff 静态检查和 pytest 11/11 通过。
- 性能脚本实际连接现有 MySQL，只读完成 3 组查询各 5 次，并生成机器相关测量收据。
- 第一次临时初始化失败后，确认没有残留名为 `insightops-clean-bootstrap` 的容器或卷；修正端口后再次实际启动，验证 `schemas=4`、`tables=20`，脚本退出清理后再次确认无临时资源残留。
- 未覆盖边界：GitHub Actions 文件已就绪，但尚未有 Git 提交或远端仓库触发实际云端执行；完整数据接入、SQLAlchemy 迁移、全量重载与浏览器增强图表 QA 仍需后续步骤。

### 延后事项

- 用户尚未注册 GitHub 账号。待用户完成注册并明确授权后，再初始化本地提交、创建远端仓库、推送当前代码并确认 GitHub Actions 的首次云端运行；在此之前不创建账号、不提交、不推送，也不把本地 `make test` 误记为云端 CI 结果。

### 证据

- `.github/workflows/quality.yml`
- `Makefile`
- `compose.clean.yml`
- `scripts/verify_clean_docker_bootstrap.sh`
- `src/benchmark_project.py`
- `tests/test_benchmark_project.py`
- `docs/engineering_delivery.md`
- `artifacts/performance/latest.json`

## 步骤 19：完整 GA4 分段导出与重接入准备

### 原定目标

为完整 92 天 GA4 公开样例建立不会受单一 CSV 大小限制、不会丢失日期、也不会覆盖现有 14 天开发批次的导出和接入路径。

### 实际完成

- 新增 `sql/bigquery/04_extract_ga4_events_drive_segment.sql`：以可修改的日期参数导出与现有 MVP 完全一致的 12 列轻量事件数据。
- 新增 `src/prepare_ga4_segmented_import.py` 与 `make prepare-ga4-full`：严格检查分段文件名、列顺序、行日期、连续日期覆盖与每段 SHA-256；仅在覆盖完整时合并 CSV，并生成包含所有段哈希和行数的 manifest。
- `src/ingest_ga4_raw.py` 改为从输入 CSV 自动推导实际起止日期和预期行数，消除此前固定 14 天日期范围的限制；导入结束时再断言已写入行数与源文件一致。
- 新增完整操作清单 `docs/ga4_full_refresh.md`：列出 14 个 7 天/末日分段、目录、命名、BigQuery 操作、接入顺序和验收门槛。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 约 429 万行事件无法安全假定为一个 Google Drive CSV | 使用连续 7 天分段和显式日期清单；若某段仍过大，必须进一步缩短相邻区间并重新校验连续覆盖 |
| 现有导入批次的日期范围被写死为 14 天 | 在创建批次前流式扫描 CSV，记录实际最小/最大事件日期和预期行数 |
| 多段手工下载容易漏段、重叠或混入字段不同的文件 | 合并器拒绝不连续日期、文件名不规范、字段顺序不一致、行日期越界和空分段，并保留每段 SHA-256 |

### 自检与测试

- 新增单元测试覆盖“连续两段能合并、记录哈希并保留行数”“日期存在空洞会阻断”“输入文件自动推导最小/最大日期”和“空事件文件阻断”四种情形；全仓静态检查与 pytest 15/15 通过。
- 未覆盖边界：完整 14 个文件尚未由用户在 BigQuery 下载，因此没有创建新 Raw 批次或重跑下游；不得将此准备工作表述为完整 GA4 已接入。

### 证据

- `sql/bigquery/04_extract_ga4_events_drive_segment.sql`
- `src/prepare_ga4_segmented_import.py`
- `src/ingest_ga4_raw.py`
- `tests/test_prepare_ga4_segmented_import.py`
- `docs/ga4_full_refresh.md`

## 2026-11-05：公开仓库安全加固

### 目标与范围

根据公开源码安全审查，修复端口暴露、测试默认密码、依赖漏洞、敏感文件忽略缺口，并完善相关输出安全与许可证。用户明确选择 MIT。此前“仅私人仓库”的发布约束已由用户公开仓库及本次修复请求更新；历史阶段记录保留。

### 实际改动

- MySQL 发布端口绑定回环地址；关闭未使用的 LOCAL INFILE。测试 Compose 独立于真实 `.env`，不发布端口，使用每次随机的 root 密码；每次独立项目隔离临时卷，退出后清理。
- 修正初始化就绪判断：等待认证 SQL 查询成功，避免 `mysqladmin ping` 在权限尚未就绪时误报成功。
- Streamlit 项目配置与启动说明固定 `127.0.0.1`；动态 HTML 字符串转义；证据包与审阅 JSON 使用 UTF-8。审阅台仍为本地 MVP，无多人认证。
- 提高受影响依赖下限，pytest 允许选择 9.0.3 以上修复版本；生成跨平台哈希锁文件。CI 使用锁文件、Python 3.11/3.14、固定 SHA 的 Actions，并运行依赖安全扫描；补充 Dependabot 配置。
- 补充人工审阅、环境变体、Streamlit secrets 与私钥忽略规则；加入 MIT、SECURITY.md，更新 README。

### 自检与测试

- 原有 22 项测试先通过；新增真实 Streamlit AppTest，先复现未转义 HTML 和 Windows 中文 JSON 解码错误，修复后通过，合计 23 项。
- Ruff、Python 编译、哈希依赖安装、pip check 与锁文件安全扫描通过，扫描未发现已知漏洞。
- 隔离 Docker 从零初始化：4 个 schema / 17 张表，无主机发布端口，临时容器、卷与网络已自动清理。
- 真实浏览器验证：动态 HTML 以文本显示，未生成注入图片元素；中文人工审阅记录成功写入并按 UTF-8 读回，未执行业务动作。
- 生产数据与全量历史回归未执行：本次隔离检出不含生产 `.env`、真实数据和历史报告。Actions 历史日志仍未完成完整审查。

## 步骤 27：私人 GitHub 发布与首次云端 CI 验证

### 原定目标

在用户注册 GitHub 并明确授权后，创建私人远端、仅提交已预检的项目源文件、完成本机身份认证、推送 `main` 分支并实际核验 GitHub Actions 的首次云端代码检查。

### 实际完成

- 用户创建私人仓库后，本地初始分支规范为 `main`，首次提交 `06edf6d` 仅包含 107 个预检项目文件：源码、SQL、测试、Notebook、文档、配置模板、CI 与空目录占位文件。
- 推送前扩展 `.gitignore`，确保 `.env`、所有数据、证据包、生成报告、性能/回归收据均不进入版本库；同时移除文档中的本机绝对路径与 Cloud 项目 ID。暂存内容通过 whitespace 和敏感模式扫描。
- 本机初次 HTTPS 推送因未认证而安全失败，未上传文件；经用户允许安装 GitHub CLI 并完成官方设备代码授权后，成功推送私人 `main` 分支。
- 首次 Quality CI 发现工作流只在系统 Python 安装依赖、而 `Makefile` 固定使用 `.venv` 的干净环境缺陷。提交 `f689b31` 后，工作流显式创建 `.venv` 并安装依赖；第二次 Quality 运行在 48 秒内通过。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 本机没有 GitHub HTTPS 凭据 | 不要求用户提供密码或 Token；经明确授权安装 GitHub CLI，使用 GitHub 官方浏览器设备授权，凭据由系统凭据存储管理。 |
| GitHub Actions 第一次失败，日志显示 `.venv/bin/ruff` 不存在 | 保持 `Makefile` 的本地可复跑契约不变；修改工作流先创建 `.venv`，再从 `requirements.txt` 安装依赖，重跑云端验证通过。 |
| 项目资料中可能包含本机路径、Cloud 项目 ID、原始数据或生成物 | 推送前采用明确 allowlist 暂存、`.gitignore` 排除与敏感模式扫描；首次提交不含上述内容。 |

### 自检与测试

- 暂存预检通过：107 个初始文件均在允许范围，`git diff --cached --check` 无错误，敏感模式扫描无本机路径、Cloud 项目 ID、邮箱、联系方式或个人身份信息命中。
- CI 修复在本机执行 `make test` 通过：37 个 Python 文件格式正确、Ruff/编译通过、pytest 22/22 通过。
- GitHub Actions Quality 第二次实际运行通过：checkout、Python 3.11、虚拟环境、依赖安装与 `make test` 全部成功。首次失败运行保留为真实历史记录，未被删除或改写。
- 未覆盖边界：私人仓库仅验证代码 CI；真实数据回归仍按设计在本地执行，不进入云端。GitHub 运行器提示依赖 action 的 Node 20 弃用，但本次被运行器兼容处理且不影响通过结论；后续可在 action 升级时再复核。

### 证据

- `.github/workflows/quality.yml`
- `.gitignore`
- `docs/execution_rules.md`
- `docs/project_state.md`
- GitHub Actions Quality 云端运行记录（私人仓库）

## 步骤 26：发布前最终交付对账与交接包

### 原定目标

以完整 92 天 GA4 批次为当前基线，核对本地 MVP 的 Definition of Done，补齐架构图、演示材料、来源登记与最终交接入口；执行代码、开发样例/合成场景和完整批次的最终回归，同时把尚未发生的外部发布事项明确隔离。

### 实际完成

- 新增 `docs/final_handoff.md`：提供已交付能力矩阵、Mermaid 架构图、可执行验证入口、数据边界及外部发布顺序。
- 新增 `docs/demo_runbook.md`：提供 3–5 分钟录屏的分段画面、话术和展示禁区；绝不把公开样例、人工复核候选或本地验证虚报为生产业务/云端结果。
- 更新 `docs/project_scope.md` 的 Definition of Done：已验证的本地项均以证据标记完成；实际视频录制和 GitHub 首次云端 CI 保持为未完成的外部事项。
- 更新 `docs/data_access.md`、`README.md`、`docs/project_state.md`、`docs/engineering_delivery.md`、`docs/regression_checks.md`，将完整 JSON 载荷、浏览器 QA 和最终交接入口与当前状态对齐。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| Definition of Done 仍保留初始未勾选状态，数据访问文档仍写完整载荷“待下载” | 不改写历史步骤总结；在范围页和当前来源登记中基于运行证据更新状态，并新增独立最终交接清单。 |
| 首次 `make check` 发现步骤 24 新增的一行统计代码未满足 Ruff 格式 | 在数据库回归开始前按 Ruff 建议格式化该行；重新执行完整检查后通过。 |
| 原范围要求实际演示视频和 GitHub 云端 CI，但二者尚未发生 | 交付录屏脚本与已就绪工作流，不将其标记为已完成；明确等待用户录制/注册账号后授权。 |

### 自检与测试

- `make check` 通过：37 个 Python 文件格式正确、编译与 Ruff 通过、pytest 22/22 通过；14 天开发样例与三个合成 Golden Question 场景只读回归为 `PASSED`。
- `make regression-full` 通过：完整 GA4 Raw/Staging 均为 4,295,584 行；质量 `SUCCEEDED`、0 条 BLOCKER 失败；92 天日指标为 5,692 / 4,786 / 4,451（购买 / 有效交易号购买 / 规范订单）；异常为 71 / 24 / 47 / 736，贡献为 15；报告结构为 14 个块、2 张指标卡、1 张图、1 张表。
- 文档交接入口、架构图、演示脚本和完整载荷来源记录已人工交叉核对；没有执行 Git 初始化、提交、远端创建、推送、外网部署或云端 CI。
- 未覆盖边界：实际 3–5 分钟录屏、GitHub 远端/首次云端 CI、外网部署、跨浏览器与无障碍人工验收、多人/RBAC 仍是明确的外部后续事项，不影响本地 MVP 完成状态。

### 证据

- `docs/final_handoff.md`
- `docs/demo_runbook.md`
- `docs/project_scope.md`
- `docs/data_access.md`
- `artifacts/regression/latest.json`
- `artifacts/regression/full_ga4_latest.json`

## 步骤 25：完整报告增强渲染与窄屏交互 QA

### 原定目标

在可用浏览器环境中实际打开完整 92 天 GA4 报告，补齐此前 `structural_only` 验证未覆盖的桌面图表、来源提示、审计表交互和窄屏响应式布局检查。

### 实际完成

- 用户启动仅监听本机的临时预览服务后，在 `http://127.0.0.1:8765/report.html` 实际打开 `full_ga4_92d` 报告。
- 桌面视图确认标题、执行摘要、两张指标卡、92 日原生覆盖率图、审计表及其分页均渲染正常；审计表可由第 1 页切换到第 2 页，且第一条记录正确为 2020-11-16。
- 指标“有效交易号覆盖率”的来源说明交互可实际打开并显示其定义；报告仍明确 71 / 24 / 47 是统计异常、人工复核候选与被抑制异常，未把样例结果升级为业务结论。
- 在 390 × 844 窄屏视口复测，`scrollWidth`、`bodyWidth` 与视口宽度均为 390px，无横向溢出；图表和表格同时保留语义化可访问结构。页面控制台无 error 或 warn。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 应用内浏览器禁止直接访问 `file://` 报告 | 不绕过浏览器安全策略；改用用户明确授权并手动启动的仅本机预览服务。 |
| 系统授权服务多次在端口监听确认时传输中断 | 未重复绕过授权；由用户在本机启动服务后继续只读浏览器 QA。 |
| 首次浏览器会话被清理后绑定失效 | 重新连接同一应用内浏览器后继续验证；没有重跑数据任务或修改报告。 |

### 自检与测试

- 桌面 DOM 与视觉截图均确认内容、图表轴、两张指标卡和审计表可见；审计表分页的状态与下一页日期实际核验通过。
- 指标定义 tooltip 实际打开；窄屏 390px 下无水平滚动，语义图表表格存在，控制台 0 条错误/警告。
- `run_full_ga4_regression.py` 的结构与数据基线仍由步骤 24 的 `PASSED` 收据约束；本步骤不写入数据库、不重建报告、也不更改原始文件。
- 未覆盖边界：此报告为本机静态交付物，不等同于外网托管、跨浏览器矩阵或无障碍人工验收；这些应在未来发布环境中按需补做。

### 证据

- `artifacts/reports/full_ga4_92d/report.html`
- `artifacts/reports/full_ga4_92d/artifact.json`
- `docs/reporting.md`

## 步骤 24：SQLAlchemy 连接层迁移与回归测试

### 原定目标

将 pandas 的 MySQL 只读查询统一迁移至 SQLAlchemy Engine，消除 PyMySQL DBAPI 兼容性警告；保留既有 PyMySQL 显式事务写入路径、SQL 语义与审计边界不变，并以完整 GA4 批次进行真实回归。

### 实际完成

- 新增 `src/db_connection.py`：集中加载本地连接配置，并分别提供带 `pool_pre_ping` 的 SQLAlchemy Engine（仅供 pandas 读取）与显式 PyMySQL 事务连接（供现有写入）。密码不会被日志或测试序列化。
- `build_ga4_daily_metrics.py` 和 `run_ga4_anomaly_detection.py` 的全部 pandas 读取均已迁移到参数化 `sqlalchemy.text()` + Engine；项目中已无 pandas 直接读取 PyMySQL DBAPI 连接的路径。写入仍使用原有 `%s` 参数化事务，未混用两种占位符。
- 为连接 URL 新增单元测试，确认使用 `mysql+pymysql`、目标 Mart schema、UTF-8 编码且渲染时隐藏密码。
- 对完整批次 `55c6501e-5403-43a4-b4d5-1a422d87b9d5` 实际重跑：日指标运行 `07d6a325-0551-405a-94de-dd514f264219` 写入 92 个日指标与 1,104 条维度记录；异常运行 `27bcd7bd-3c48-45dd-830d-d1ce73d44c8f` 识别 71 个统计异常和 15 条贡献。运行中未出现 pandas/PyMySQL 兼容性警告。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 首次静态检查需要写 Ruff 缓存，授权通道在返回前发生网络中断 | 改用 Ruff `--no-cache`、pytest 禁用缓存与字节码写入的等价只读检查；不规避授权，也不修改数据库。 |
| 直接执行 pytest 时漏掉项目标准的 `PYTHONPATH=src` | 依照 `Makefile` 的既定测试环境重跑，22/22 通过；这不是代码导入或迁移缺陷。 |
| 异常脚本首次把所有不可业务解释的检测行计为“被抑制异常” | 限定为“统计异常且不可业务解释”的交集，日志现明确输出 `suppressed_anomalies`；完整基线正确为 47，而不是 432 条普通/历史不足检测行。 |

### 自检与测试

- Ruff 静态检查通过；项目标准 `PYTHONPATH=src` 下 pytest 22/22 通过。
- 实际 MySQL 回归生成新的日指标与异常审计运行；日指标为 92 天、维度记录为 1,104，异常为 71、贡献为 15。
- `run_full_ga4_regression.py` 只读对账通过：Raw/Staging 均为 4,295,584 行，92 日指标为 5,692 / 4,786 / 4,451（购买 / 有效交易号购买 / 规范订单），异常为 71 / 24 / 47 / 736，贡献为 15，报告结构为 14 个块、2 张指标卡、1 张图、1 张表。
- 未覆盖边界：SQLAlchemy 在本步骤仅用于 pandas 只读查询；其余脚本保留显式 PyMySQL 事务是有意的写入语义边界。报告的浏览器增强渲染与窄屏交互 QA 仍待稳定 Chrome 环境完成。

### 证据

- `src/db_connection.py`
- `src/build_ga4_daily_metrics.py`
- `src/run_ga4_anomaly_detection.py`
- `tests/test_db_connection.py`
- `artifacts/regression/full_ga4_latest.json`
- `docs/engineering_delivery.md`

## 步骤 23：GA4 JSON 商品与参数最小派生模型

### 原定目标

将完整载荷的 `items_json` 与 `event_params_json` 以独立数组粒度展开，并验证不会出现商品×参数的笛卡尔倍增、键重复、数组截断或值类型混淆。

### 实际完成

- 新增两张版本化 Staging 表：`ga4_item_event_stg` 为一行一个商品数组元素，`ga4_event_param_stg` 为一行一个白名单参数键；两者均可追溯到单个 Raw 事件、原始质量运行和派生运行，且绝不互相 join。
- 商品/参数派生运行 `906bc6e7-c24e-4c95-88f2-e29cd272f313` 成功写入 18,804,202 行：3,982,732 个商品行、14,821,470 个白名单参数行，并识别 1,393 个非占位商品 ID。
- 商品质量运行 `a0a4d764-00ec-450e-b448-8fc5dfe86dff`、参数质量运行 `c701973b-1bbd-45d5-ac67-d67015ad3f6c` 均为 `SUCCEEDED`、0 条 BLOCKER 失败。Notebook `notebooks/08_ga4_json_derivatives_audit.ipynb` 已顶到底执行。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 本地命令输出通道中断，但 MySQL 实际仍在后台执行完整参数插入 | 通过全量 processlist 定位运行中的事务并等待其原子提交；不重复启动派生写入。随后发现首个命令也后台启动了一套质量门禁，因此只读等待两套独立质量运行完成，并核对其结果一致。 |
| Notebook 首次将 kernel 工作目录误当作项目根目录 | 改为从 `notebooks/` 的父目录解析项目根路径，重新顶到底执行成功。 |

### 自检与测试

- 商品模型 3 条 BLOCKER 全通过：源 `items_json` 数组长度逐事件对账、`raw_event_id + item_index` 唯一、单事件数组长度不超过 100。
- 参数模型 3 条 BLOCKER 全通过：白名单源键逐行对账、`raw_event_id + parameter_name` 唯一、每行最多一个 string/int/float/double 值。
- 商品 WARNING：130,641 行缺可用商品 ID/名称，1 行金额为负；参数 WARNING：2,080,202 行白名单参数无值。均保留为质量信号，不伪造或删除 Raw JSON。
- Ruff、Python 编译、静态检查与 pytest 21/21 通过；审计 Notebook 已执行。

### 证据

- `sql/ddl/10_ga4_json_derivatives.sql`
- `sql/migrations/003_ga4_json_derivative_tables.sql`
- `src/build_ga4_json_derivatives.py`
- `src/run_ga4_json_quality.py`
- `src/ga4_json_derivative_contract.py`
- `tests/test_ga4_json_derivative_contract.py`
- `notebooks/08_ga4_json_derivatives_audit.ipynb`

## 步骤 22：完整 GA4 批次报告与回归基线适配

### 原定目标

让完整 92 天 JSON 批次拥有独立、可审计的报告和回归入口，同时保留旧 14 天开发样例、合成场景及其结论边界，不发生默认数据源覆盖。

### 实际完成

- `src/build_report_artifacts.py` 新增显式 `--include-full-ga4` 开关及完整批次常量；默认仍只生成旧 14 天正常周报和合成异常报告，完整报告独立写入 `artifacts/reports/full_ga4_92d/`。
- 新报告绑定完整批次 `55c6501e-5403-43a4-b4d5-1a422d87b9d5`、Raw 质量运行 `0d9b0ba3-04fd-4adf-a1c8-e2543c79b01f`、日指标运行 `3d901694-d802-4231-8f02-f7d25fea7a76` 与异常运行 `5f4195cc-0b42-4fbb-bc2c-fc728b46b9b8`；显示 4,295,584 条事件、92 天、5,692 个购买事件、84.1% 整体有效交易号覆盖率、4,451 个规范订单，以及 71 / 24 / 47（统计 / 可供人工复核 / 抑制）异常状态。
- 新增 `src/run_full_ga4_regression.py` 和 `make regression-full`：只读对账接入、Raw、Staging、质量门禁、日指标、异常、贡献与完整报告 artifact，收据为 `artifacts/regression/full_ga4_latest.json`。
- 更新 `docs/reporting.md`、`docs/regression_checks.md`、`README.md` 与状态检查点；报告摘要中的每条定量主张按来源拆分绑定，避免混合来源的单一 markdown 块无法追溯。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 旧报告生成器将 batch/run ID 固定为 14 天样例 | 保留旧路径不动，增加显式完整批次开关和独立输出目录，防止新数据静默替换既有报告或回归。 |
| 数据库画像最初假定了不存在的 `rows_read` 与 `quality_check_result` 字段/表 | 通过只读 `SHOW COLUMNS` 与 information_schema 定位实际的 `rows_loaded`、`data_quality_run` 与 `data_quality_result` 审计结构；报告与回归只引用已确认表。 |
| 质量门禁有 2 条 WARNING，可能被误表述为“所有规则通过” | 报告明确为 11 条 BLOCKER 全通过；不掩盖 WARNING，交易号覆盖守护和人工复核边界继续生效。 |
| 打包器没有可用的无头 Chromium | canonical artifact、来源、快照和语义 HTML 回退已通过 `structural_only` 验证；没有下载浏览器或重复尝试，增强图表、窄屏和来源交互 QA 留为明确未覆盖项。 |

### 自检与测试

- `make format && make test` 通过：Ruff 格式/静态检查、Python 编译及 pytest 19/19 全部通过；新增独立完整报告契约 fixture。
- 实际生成完整报告并执行 `make regression-full`：Raw 与 Staging 均为 4,295,584 行；质量为 `SUCCEEDED`、0 条 BLOCKER 失败；92 日指标、71 / 24 / 47 / 736 异常结果和 15 条贡献均与固定基线一致。
- 自包含 `report.html` 通过报告打包器 validation、package 与 structural verification；生成 14 个报告块、1 个原生折线图、2 个指标卡和 1 个 92 日审计表，含可读无脚本语义回退。
- 未覆盖边界：本机未找到兼容 Chromium headless-shell，因此未完成增强阅读器的图表 SVG、桌面/窄屏布局与来源交互自动化 QA；这是环境能力缺失，不影响已完成的结构化交付和数据库对账。

### 证据

- `src/build_report_artifacts.py`
- `src/run_full_ga4_regression.py`
- `tests/test_report_artifact_contracts.py`
- `artifacts/reports/full_ga4_92d/report.md`
- `artifacts/reports/full_ga4_92d/artifact.json`
- `artifacts/reports/full_ga4_92d/report.html`
- `artifacts/regression/full_ga4_latest.json`
- `docs/reporting.md`
- `docs/regression_checks.md`

## 步骤 21：完整 GA4 JSON 载荷接入与核心分析链路重跑

### 原定目标

将验收通过的 92 天、完整 `event_params_json` / `items_json` GA4 文件以新的 append-only 批次接入 MySQL，并在不覆盖 14 天开发样本的前提下重新执行质量门禁、Staging、订单、漏斗、日指标、异常检测、Evidence Package 与受限 Agent。

### 实际完成

- 15 个连续分段已合并为 9.5GB 完整载荷 CSV；manifest 为 `full_json`、92 天、4,295,584 行，精确匹配 BigQuery profile，合并 SHA-256 为 `52694651cfcbb098c9e56424cce32382ca862167b9dfb82e7b5de042a20d69c6`。
- 首次 Raw 导入批次 `c2f20e50-a4dc-4d0f-b0e4-baa4700aa202` 在 1,815,000 行处失败并保留审计；修复 BigQuery 整数秒时间戳解析后，以新批次 `55c6501e-5403-43a4-b4d5-1a422d87b9d5` 成功追加全部 4,295,584 行。旧 14 天批次和失败批次均未删除或覆盖。
- `ga4_raw_v2` 质量运行 `0d9b0ba3-04fd-4adf-a1c8-e2543c79b01f` 的 11 条 BLOCKER 全部通过；完整批次 Staging 写入 4,295,584 行，购买事件为 5,692、订单资格购买事件为 5,669。
- 新订单事实运行 `400d262a-1279-4ab7-a4e7-e365b8e978a2` 产生 4,451 个去重规范订单；新会话漏斗运行 `fb94bd70-d1df-47ea-8a7b-5e5fed3a6f67` 产生 360,129 个会话。
- 日指标运行 `3d901694-d802-4231-8f02-f7d25fea7a76` 写入 92 个日指标与 1,104 条维度切片；异常运行 `5f4195cc-0b42-4fbb-bc2c-fc728b46b9b8` 写入 736 条检测结果、71 条统计异常、15 条贡献记录。
- 生成 `artifacts/evidence_packages/ga4_full_v2_evidence.json` 与 `artifacts/run_traces/ga4_full_v2_agent_response.json`：71 个统计发现，其中 24 个满足业务解释条件、47 个被守护抑制；受限 Agent 输出 28 条带引用且要求人工复核的结构化主张。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 完整 CSV 同时含带微秒和不带微秒的 BigQuery 时间戳，旧解析器仅接受前者 | 改用 `datetime.fromisoformat` 解析移除 UTC 后缀的 ISO 时间，新增两种格式的单元测试；失败批次保留，新批次全量重试 |
| 92 天完整 JSON 导入、Staging 与会话聚合远大于开发样本 | 以新批次、原子 Staging 事务和运行审计逐层执行；每一步以数据库行数和运行状态核验，未并行写入相同目标 |
| 完整样本仍存在交易号语义问题 | 质量门禁将 1,544 条重复购买交易号受影响行和 23 条缺交易号购买事件记录为 WARNING；不阻断事件分析，但订单/收入解释继续受到 95% 覆盖守护限制 |
| 现有报告生成器固定读取旧 14 天 batch/run ID | 未冒险重跑或覆盖报告；明确列为下一步参数化改造任务 |

### 自检与测试

- 完整合并清单、行数、日期范围和 BigQuery 基准独立对账通过；成功 Raw 批次为 4,295,584 行，Staging 行数精确一致。
- 修复后全仓 Ruff 格式、Python 编译、Ruff 静态检查与 pytest 18/18 通过。
- Raw 质量门禁的 11 条 BLOCKER 全通过、拒绝记录为 0；Staging、订单、会话、日指标、异常运行均为成功状态。
- 异常数据库独立对账：92 日，覆盖率均值 79.1110%、范围 0%–100%；71 条统计异常 = 24 条可解释 + 47 条抑制，贡献记录为 15。
- 未覆盖边界：完整 JSON 已被 Raw 保留，但尚未展开为商品/额外参数事实；报告、回归基线和审阅台的默认选择仍指向旧 14 天批次，必须参数化后再生成完整样例交付物。

### 证据

- `data/staged/ga4/ga4_ecommerce_events_20201101_20210131.manifest.json`（本地忽略文件）
- `src/ingest_ga4_raw.py`
- `tests/test_ingest_ga4_raw.py`
- `artifacts/evidence_packages/ga4_full_v2_evidence.json`
- `artifacts/run_traces/ga4_full_v2_agent_response.json`
- `docs/ga4_full_refresh.md`

## 步骤 20：GA4 完整 JSON 载荷支持与分段回退

### 原定目标

在不牺牲现有 12 列分析路径的前提下，优先保留完整 `event_params` 和 `items` 原始 JSON，先尝试 7 天连续分段导出；若超限，按明确的更短分段与云端分片路径处理。

### 实际完成

- 新增 `sql/bigquery/05_extract_ga4_events_full_drive_segment.sql`：输出 14 列，包括 `event_params_json` 与 `items_json`，默认尝试 2020-11-01 至 2020-11-07。
- 新增可重复迁移 `sql/migrations/002_ga4_full_payload_columns.sql`，并已在本地 MySQL 实际执行：`insightops_raw.ga4_event_raw` 的两列均为可空 JSON；未修改已有轻量批次行。
- `src/ingest_ga4_raw.py` 与分段合并器同时支持严格的 12 列轻量和 14 列完整载荷契约；完整载荷会写入 Raw，Staging 保持既有字段，后续可按需从 Raw 展开，避免混改当前指标。
- 更新完整导出指南与数据访问登记：7 天完整载荷失败时先改为 1 天连续分段；若仍失败，先明确说明，再评估结算账号下的 Cloud Storage Parquet 或针对业务问题的选择性字段导出。

### 遇到的问题与解决

| 问题 | 解决方式 |
| --- | --- |
| 当前 Raw 表没有保存 JSON 的列 | 通过安全、幂等的 information_schema 检查迁移新增两列；在实际主容器中查询确认类型为 `json`、允许空值 |
| 轻量和完整文件的字段不同，混合后可能使合并/导入静默错位 | 仅接受精确的 12 列或 14 列契约；合并器要求所有分段字段完全相同，并把 `payload_mode` 与列清单写入 manifest |
| 不能预先断言 7 天完整 JSON 一定能经 Drive 导出 | 将 7 天作为最高优先级尝试，1 天为最小降级，Cloud Storage Parquet/选择性字段为后续明确决策；不把尚未成功的下载写成已完成 |

### 自检与测试

- 全仓 Ruff 格式、Python 编译、Ruff 静态检查与 pytest 17/17 通过；测试覆盖轻量文件、完整 JSON 文件、连续分段、日期空洞阻断、日期范围推导及完整载荷 manifest 标记。
- 实际 Docker/MySQL 迁移和查询通过：`event_params_json | json | YES`、`items_json | json | YES`。
- 未覆盖边界：尚未由 BigQuery 实际导出第一段完整 JSON CSV，也未创建新数据批次；完整样例的最终体积、下载可行性、数据质量和新业务结论仍必须以实际导出后的审计为准。
- 浏览器自动化尝试打开并读取 BigQuery 查询界面时发生页面连接超时；两次均未输入 SQL、未运行查询或创建下载任务。保留用户手动在已登录页面运行首个 7 天查询的路径，文件出现后再继续自动化接入。

### 证据

- `sql/bigquery/05_extract_ga4_events_full_drive_segment.sql`
- `sql/migrations/002_ga4_full_payload_columns.sql`
- `src/ingest_ga4_raw.py`
- `src/prepare_ga4_segmented_import.py`
- `tests/test_ingest_ga4_raw.py`
- `tests/test_prepare_ga4_segmented_import.py`
- `docs/ga4_full_refresh.md`
