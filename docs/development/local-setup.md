# 本地开发

详细环境变量、启动、测试与静态检查命令见项目根目录 README.md。Windows 开发建议使用 PowerShell、Node.js 24、Python 3.12+ 和 Docker Desktop。

.env.example 是变量模板。复制为 .env 后可按需修改本地数据库用户名和密码。容器之间使用 Compose 服务名访问数据库与 Redis，宿主机运行后端使用 localhost 地址。