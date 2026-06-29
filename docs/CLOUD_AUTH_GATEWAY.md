# 云服务器认证网关设计

本文记录智哨公网看护页的账号登录、管理员用户管理和云端认证网关方案。

## 目标

- 将公网看护页的账号体系放在云服务器，不放在 RDK。
- 用网页登录页替代浏览器 Basic Auth 弹窗。
- 管理员可以增删改用户，普通用户只能访问看护页。
- 密码只保存哈希，不保存明文。
- RDK 主程序继续专注摄像头、姿态检测、云台、飞书和本地看护页，不承担公网账号管理。

## 非目标

第一阶段不做以下能力：

- 公开注册。
- 邮箱或短信验证码。
- 找回密码。
- 第三方登录。
- 多设备、多家庭、多老人绑定。
- 复杂权限组。
- 审计报表后台。

## 总体架构

```text
用户浏览器
  -> 云服务器 Nginx
  -> 云端认证网关
  -> 已登录后反向代理到 RDK Web 看护页
  -> RDK X5 本地看护服务
```

云服务器负责：

- 登录页。
- 退出登录。
- 登录会话。
- 用户数据库。
- 管理员用户管理。
- 认证后转发公网请求到 RDK。

RDK 负责：

- `/` 看护页面。
- `/health` 健康检查。
- `/api/status` 状态数据。
- `/api/command` 看护命令。
- `/video/skeleton` 脱敏视频流。
- `/video/raw` 真实画面流，仍由 RDK 侧隐私复核控制。

## 账号与权限

第一阶段只有两种角色：

```text
admin  管理员
user   普通用户
```

管理员可以：

- 登录。
- 退出登录。
- 访问看护页面。
- 查看用户列表。
- 新增用户。
- 修改用户密码。
- 启用或禁用用户。
- 删除普通用户。

普通用户可以：

- 登录。
- 退出登录。
- 访问看护页面。
- 使用看护页面已有按钮。

普通用户不可以：

- 访问用户管理页。
- 创建用户。
- 删除用户。
- 修改其他用户密码。
- 删除管理员。

## 注册策略

不开放公开注册。

原因：

- 公网入口暴露在互联网，公开注册会增加攻击面。
- 比赛演示时，管理员创建用户更容易解释安全边界。
- 后续如果需要家庭成员自助申请，可以再增加“申请账号，管理员审核”的流程。

## 数据库设计

账号数据保存在云服务器 SQLite 数据库中。

建议路径：

```text
/opt/zhishao-auth/zhishao_auth.db
```

用户表：

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT DEFAULT ''
);
```

字段说明：

- `username`：登录用户名，唯一。
- `password_hash`：Werkzeug 或同等级安全库生成的密码哈希。
- `role`：`admin` 或 `user`。
- `enabled`：`1` 启用，`0` 禁用。
- `created_at` / `updated_at`：账号维护时间。
- `last_login_at`：最近登录时间。

## 会话设计

云端认证网关使用服务端签名 Cookie 保存登录状态。

建议配置：

```text
session cookie httponly
session cookie samesite=lax
session cookie secure=false  # HTTP 阶段先关闭，切到 HTTPS 后改为 true
```

登录成功后，Session 中只保存必要字段：

```text
user_id
username
role
```

不在 Cookie 中保存密码、密码哈希、DashScope Key、飞书配置或 RDK 敏感配置。

## 路由设计

认证网关自身路由：

```text
GET  /login          登录页
POST /login          提交登录
POST /logout         退出登录
GET  /admin/users    用户管理页，仅 admin
POST /admin/users    新增用户，仅 admin
POST /admin/users/<id>/password  修改密码，仅 admin
POST /admin/users/<id>/toggle    启用/禁用，仅 admin
POST /admin/users/<id>/delete    删除用户，仅 admin
GET  /auth/verify    Nginx auth_request 校验入口
```

反向代理受保护路径：

```text
/
/health
/api/status
/api/command
/video/skeleton
/video/raw
```

所有受保护路径都必须先通过登录校验。

## Nginx 接入设计

Nginx 负责对公网入口做统一拦截。

推荐思路：

```text
公网请求
  -> /login /logout /admin/users 直接转发给认证网关
  -> 其他路径先调用 /auth/verify
  -> 校验通过后转发到 RDK 看护页
  -> 校验失败跳转 /login
```

示意配置：

```nginx
location /auth/verify {
    internal;
    proxy_pass http://127.0.0.1:9100/auth/verify;
}

location /login {
    proxy_pass http://127.0.0.1:9100;
}

location /logout {
    proxy_pass http://127.0.0.1:9100;
}

location /admin/ {
    proxy_pass http://127.0.0.1:9100;
}

location / {
    auth_request /auth/verify;
    error_page 401 =302 /login;
    proxy_pass http://127.0.0.1:5000;
}
```

上面的 `127.0.0.1:5000` 只是示意上游。实际部署前必须先读取云服务器当前 Nginx 配置，沿用已经验证可访问 RDK 看护页的上游地址，不能直接覆盖现有转发目标。

## 初始化管理员

认证服务启动时，如果数据库里没有管理员账号，允许通过一次性命令初始化：

```bash
python3 app.py create-admin <username>
```

命令执行后交互输入密码，密码不显示在终端。

不建议把初始管理员密码写入代码、`.env`、Shell 历史或 Git。

## 安全策略

第一阶段必须做到：

- 密码哈希保存，不保存明文。
- 禁止公开注册。
- 用户名唯一。
- 禁用账号不能登录。
- 普通用户不能访问 `/admin/users`。
- 普通用户不能删除或修改其他用户。
- 管理员不能删除自己的最后一个管理员账号。
- 所有表单使用 POST 执行写操作。
- 登录失败只提示“用户名或密码错误”，不暴露用户是否存在。

建议后续增强：

- HTTPS 域名。
- 登录失败次数限制。
- CSRF Token。
- 管理操作审计日志。
- 更细粒度的家庭成员权限。

## 部署与回滚

部署顺序：

1. 在云服务器创建认证服务目录。
2. 安装 Python 虚拟环境和依赖。
3. 初始化 SQLite 数据库。
4. 创建管理员账号。
5. 以 systemd 启动认证服务。
6. 调整 Nginx，把公网入口接入认证网关。
7. `nginx -t` 检查配置。
8. `systemctl reload nginx` 生效。
9. 用浏览器验证登录、退出、用户管理和看护页访问。

回滚方式：

1. 恢复 Nginx 到接入认证网关前的配置。
2. `nginx -t`。
3. `systemctl reload nginx`。
4. 停止认证服务。

RDK 正式目录不参与本次功能改造。

## 测试计划

本地或云端只读验证：

- Python 语法检查。
- 认证服务单元测试。
- 用户表初始化测试。
- 密码哈希验证测试。
- 登录成功和失败测试。
- 禁用用户不能登录测试。
- 普通用户不能访问管理页测试。
- 管理员可以增删改用户测试。

云服务器联调验证：

- 未登录访问 `/` 会跳转 `/login`。
- 登录成功后可以访问看护页。
- 退出后再次访问看护页会跳转 `/login`。
- 管理员可以进入 `/admin/users`。
- 普通用户访问 `/admin/users` 返回拒绝。
- 禁用用户登录失败。
- RDK 看护页的视频流、状态接口和按钮仍可正常使用。

## 第一阶段交付范围

第一阶段交付以下内容：

- 云服务器认证服务代码。
- 云服务器用户数据库初始化逻辑。
- 登录页。
- 管理员用户管理页。
- systemd 服务说明。
- Nginx 接入说明。
- 基础测试。

第一阶段不修改 RDK 核心业务逻辑。
