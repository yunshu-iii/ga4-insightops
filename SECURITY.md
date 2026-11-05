# 安全与本地运行

本项目是公开样例数据的本地分析 MVP。公开仓库不会自动启动数据库或审阅台。

## 默认边界

- MySQL 仅通过 `127.0.0.1` 发布端口；`.env` 中的密码应由使用者单独生成，不得保留示例占位值。
- 审阅台通过 `.streamlit/config.toml` 仅监听 `127.0.0.1`。不要把监听地址改为 `0.0.0.0`、配置公网端口转发或直接开放云防火墙。它没有多人身份认证，自填审阅角色不能证明身份。
- 干净初始化验证使用独立 Compose 项目和卷，不发布任何主机端口；每次随机生成密码，退出后只清理该次临时项目。运行需要 Docker、Bash 和 OpenSSL。
- `.env.*`、Streamlit secrets、私钥和本地人工审阅记录均不应提交；`.env.example` 是无真实凭据的例外。
- 所有分析数据、结果和审阅内容继续留在本地。不要在公开 issue 中粘贴凭据或真实用户数据。

## 依赖更新

`requirements.txt` 记录允许的直接依赖，`requirements.lock` 记录跨平台、Python 3.11 及以上的解析结果和下载哈希。安装：

```bash
python -m pip install --require-hashes -r requirements.lock
```

更新依赖时，用安装于开发环境的 uv 重新生成锁文件，运行项目测试和安全扫描后一起提交：

```bash
uv pip compile requirements.txt --python-version 3.11 --universal --generate-hashes --no-header --no-annotate -o requirements.lock
make test
python -m pip_audit -r requirements.lock --no-deps --disable-pip
```

最后一条需要单独安装 pip-audit。GitHub Actions 会对锁文件运行同类检查；Dependabot 每周检查 Python 与 Actions 更新。依赖公告更新后，已有锁文件也可能需要升级。

## 已有本地数据库

更新端口绑定后，需要重新创建容器才能应用映射，正常数据卷会保留：

```bash
docker compose up -d
```

不要运行 `docker compose down -v`，它会删除数据库卷。更改 `.env` 中的初始化密码不会自动更改已有 MySQL 用户的密码。

当前历史数据脚本默认使用本地 root 凭据。生产或共享使用前，应按所需 schema 创建最小权限账号，并用 `MYSQL_USER` 配置；凭据字段仍遵循当前脚本接口。不要将本地 root 管理接口开放给其他机器。该项目没有声明支持生产部署。

## 报告安全问题

若仓库的 Security 页面提供 “Report a vulnerability”，请使用该私密入口。否则先通过维护者 GitHub 主页公开的联系方式取得联系；公开 issue 只提供不含利用细节、凭据或个人数据的摘要。
