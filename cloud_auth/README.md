# ZhiShao Cloud Auth Gateway

云服务器认证网关用于替代公网看护页的浏览器 Basic Auth 弹窗。

## 功能

- 登录页。
- 退出登录。
- Nginx `auth_request` 校验入口：`/auth/verify`。
- 管理员用户管理页：`/admin/users`。
- 管理员创建用户、改密码、启用/禁用、删除普通用户。
- SQLite 保存用户，密码只保存哈希。

## 本地验证

```bash
python -m unittest cloud_auth.tests.test_auth_gateway
python -m cloud_auth.app --db /tmp/zhishao_auth.db create-admin admin
python -m cloud_auth.app --db /tmp/zhishao_auth.db serve --host 127.0.0.1 --port 9100
```

访问：

```text
http://127.0.0.1:9100/login
http://127.0.0.1:9100/admin/users
```

## 云服务器部署建议

```bash
sudo mkdir -p /opt/zhishao-auth
sudo chown -R ubuntu:ubuntu /opt/zhishao-auth
cd /opt/zhishao-auth
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m cloud_auth.app create-admin admin
```

生成一个长随机密钥并写入 systemd 环境变量：

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

然后安装服务：

```bash
sudo cp deploy/zhishao-auth.service /etc/systemd/system/zhishao-auth.service
sudo systemctl daemon-reload
sudo systemctl enable --now zhishao-auth
sudo systemctl status zhishao-auth --no-pager
```

## Nginx 接入

先备份当前 Nginx 配置，并读取当前已经可用的 RDK 上游地址。

```bash
sudo nginx -T | less
```

参考：

```text
deploy/nginx-auth-gateway.conf.example
```

替换示例里的 `zhishao_rdk_monitor` 上游后再执行：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 回滚

```bash
sudo systemctl stop zhishao-auth
sudo systemctl disable zhishao-auth
sudo cp /path/to/nginx-backup.conf /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```
