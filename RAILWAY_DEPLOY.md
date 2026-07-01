# Railway 部署说明

本项目已按 Railway Docker Web Service 准备：FastAPI 后端托管 `/api/*`，并同时托管 `frontend/dist` 静态前端。

## 部署方式

推荐使用 Railway Dashboard 从 GitHub 仓库导入：

1. 将本项目推送到 GitHub 仓库。
2. 打开 Railway Dashboard，选择 `New Project`。
3. 选择 `Deploy from GitHub repo`。
4. 选择本仓库。
5. Railway 会读取根目录 `railway.json`，使用根目录 `Dockerfile` 构建。
6. 部署成功后，在服务的 `Settings -> Networking` 里生成 Public Domain。

## 必需环境变量

在 Railway 服务的 `Variables` 中配置：

```text
APP_SECRET_KEY=replace-with-a-long-random-secret
SENSEAUDIO_BASE_URL=https://api.senseaudio.cn
SENSEAUDIO_CHAT_ENDPOINT=/v1/chat/completions
SENSEAUDIO_MODEL=senseaudio-s2
```

`PORT` 由 Railway 自动注入，不需要手动配置。

## 验证

部署成功后访问：

```text
https://<your-railway-domain>/
https://<your-railway-domain>/api/health
```

`/api/health` 应返回：

```json
{"status":"ok"}
```

## 说明

当前默认使用 SQLite，容器重建后数据可能丢失。展示阶段可用；长期运行建议后续切换 Railway PostgreSQL。

SenseAudio API Key 由用户登录后在系统页面保存，不应写入代码或镜像。
