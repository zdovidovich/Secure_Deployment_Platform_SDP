# SDP (Secure Deployment Platform)

### Verified working on distros:

- Ubuntu (Ubuntu Server 24.04.4 LTS)
- Debian (12)
- RHEL (Rocky Linux 10.1)
- CentOS (10)
- Fedora (Fedora Server 43)

### Requirements

1. Master Node 

Install using Docker:

```
docker pull f0ra1n/sdp
docker run -p {your_host_port}:8080 -d f0ra1n/sdp
```

Install directly on your pc:

Requirements:

- only Linux
- python3
- Ansible (tested on core == 2.20)
- git 
- trivy
- hadolint
- community.docker for ansible-galaxy (`ansible-galaxy collection install community.docker`)

```
git clone https://github.com/zdovidovich/Secure_Deployment_Platform_SDP.git
cd Secure_Deployment_Platform_SDP
python3 -m venv .venv
.venv/bin/pip install -r app/requirements.txt
.venv/bin/python3 ./app/app.py
```
### API

The application now exposes a lightweight HTTP API from the same monolith.

- `GET /api/v1/health` - healthcheck
- `POST /api/v1/deployments` - start deployment
- `GET /api/v1/deployments/<deployment_id>` - get deployment status/result
- `GET /api/v1/deployments/<deployment_id>/events` - stream deployment logs over SSE

`POST /api/v1/deployments` expects `multipart/form-data` with the same fields as the web form.

Required:

- `ssh_key` (SSH private key file)

The image can be provided in one of two ways (select via `image_source` field, default `tar`):

1. **Tar archive** (`image_source=tar`) — upload a `docker save` archive:
   - `docker_image` (required) — `.tar` archive created with `docker save -o image.tar name:tag`
2. **Registry image** (`image_source=registry`) — pull an image from a registry on the target server:
   - `app_deploy_image_name` — full image reference (e.g. `myapp:latest` or `registry.example.com/myapp:latest`). The registry is detected automatically from this value.
   - `app_deploy_registry_username` (optional) — registry login
   - `app_deploy_registry_credential` (optional) — registry password/token

Optional:

- `dockerfile` — Dockerfile for Hadolint static analysis

If `SDP_API_KEY` is set in the environment, API requests must include header `X-API-Key: <value>`.

#### Example: deploy via curl (tar archive)

```bash
curl -X POST http://sdp.example.com:8080/api/v1/deployments \
  -H "X-API-Key: your-api-key" \
  -F "ssh_key=@./id_rsa" \
  -F "image_source=tar" \
  -F "docker_image=@./myapp.tar" \
  -F "app_deploy_image_name=myapp:latest" \
  -F "app_deploy_container_name=myapp" \
  -F "app_host_port=8080" \
  -F "app_container_port=80" \
  -F "ansible_host=192.168.1.100" \
  -F "ansible_port=22" \
  -F "ansible_user=ubuntu"
```

Response (HTTP 202):

```json
{
  "deployment_id": "a1b2c3d4",
  "status": "pending",
  "created_at": "2026-11-13T...",
  "status_url": "/api/v1/deployments/a1b2c3d4",
  "events_url": "/api/v1/deployments/a1b2c3d4/events",
  "web_url": "/deploy/status/a1b2c3d4"
}
```

#### Example: deploy via curl (registry image)

```bash
curl -X POST http://sdp.example.com:8080/api/v1/deployments \
  -H "X-API-Key: your-api-key" \
  -F "ssh_key=@./id_rsa" \
  -F "image_source=registry" \
  -F "app_deploy_image_name=registry.example.com/myapp:latest" \
  -F "app_deploy_registry_username=myuser" \
  -F "app_deploy_registry_credential=mytoken" \
  -F "app_deploy_container_name=myapp" \
  -F "app_host_port=8080" \
  -F "app_container_port=80" \
  -F "ansible_host=192.168.1.100" \
  -F "ansible_port=22" \
  -F "ansible_user=ubuntu"
```

The registry is detected automatically from the image name (e.g. `registry.example.com`, `ghcr.io`, `docker.io`). Omit username/credential for public images.

#### Check deployment status

```bash
curl -H "X-API-Key: your-api-key" \
  http://sdp.example.com:8080/api/v1/deployments/a1b2c3d4
```

Response:

```json
{
  "deployment_id": "a1b2c3d4",
  "status": "success",
  "servers": [...],
  "result": { "success": true, "message": "Деплой успешно завершён", ... }
}
```

Possible `status` values: `pending`, `running`, `success`, `error`.

### Integration with CI/CD (GitLab CI example)

SDP exposes a simple HTTP API, so integrating it into any CI/CD system comes down to a `curl` call to `POST /api/v1/deployments` followed by polling the status until the deployment finishes.

#### 1. Configure CI/CD variables

In GitLab project settings (CI/CD → Variables) add:

| Variable | Description |
|----------|-------------|
| `SDP_URL` | SDP base URL, e.g. `https://sdp.example.com:8080` |
| `SDP_API_KEY` | API key (if `SDP_API_KEY` env is set on the SDP side) |
| `SSH_PRIVATE_KEY` | Private SSH key for connecting to target servers |
| `REGISTRY_USER` | Registry login (for private images) |
| `REGISTRY_PASSWORD` | Registry password/token |
| `DEPLOY_IMAGE` | Full image reference, e.g. `registry.example.com/myapp:${CI_COMMIT_SHORT_SHA}` |
| `DEPLOY_HOST` | Target server IP |
| `DEPLOY_USER` | SSH user on the target server |

#### 2. `.gitlab-ci.yml`

```yaml
stages:
  - deploy

deploy_to_sdp:
  stage: deploy
  image: curlimages/curl:latest
  script:
    - |
      echo "Starting deployment to SDP..."
      RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${SDP_URL}/api/v1/deployments" \
        -H "X-API-Key: ${SDP_API_KEY}" \
        -F "ssh_key=@-;type=application/octet-stream" <<< "${SSH_PRIVATE_KEY}" \
        -F "image_source=registry" \
        -F "app_deploy_image_name=${DEPLOY_IMAGE}" \
        -F "app_deploy_registry_username=${REGISTRY_USER}" \
        -F "app_deploy_registry_credential=${REGISTRY_PASSWORD}" \
        -F "app_deploy_container_name=myapp" \
        -F "app_host_port=8080" \
        -F "app_container_port=80" \
        -F "ansible_host=${DEPLOY_HOST}" \
        -F "ansible_port=22" \
        -F "ansible_user=${DEPLOY_USER}")

      HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
      BODY=$(echo "$RESPONSE" | sed '$d')

      if [ "$HTTP_CODE" != "202" ]; then
        echo "ERROR: SDP returned HTTP $HTTP_CODE"
        echo "$BODY"
        exit 1
      fi

      DEPLOYMENT_ID=$(echo "$BODY" | grep -o '"deployment_id": *"[^"]*"' | cut -d'"' -f4)
      echo "Deployment started: $DEPLOYMENT_ID"

    - |
      # Poll deployment status until it finishes
      for i in $(seq 1 120); do
        STATUS_RESPONSE=$(curl -s -w "\n%{http_code}" -H "X-API-Key: ${SDP_API_KEY}" \
          "${SDP_URL}/api/v1/deployments/${DEPLOYMENT_ID}")
        HTTP_CODE=$(echo "$STATUS_RESPONSE" | tail -n1)
        STATUS_BODY=$(echo "$STATUS_RESPONSE" | sed '$d')

        STATUS=$(echo "$STATUS_BODY" | grep -o '"status": *"[^"]*"' | cut -d'"' -f4)
        echo "Poll $i/120: status=$STATUS"

        if [ "$STATUS" = "success" ]; then
          echo "DEPLOYMENT SUCCESSFUL"
          echo "$STATUS_BODY"
          exit 0
        elif [ "$STATUS" = "error" ]; then
          echo "DEPLOYMENT FAILED"
          echo "$STATUS_BODY"
          exit 1
        fi

        sleep 10
      done

      echo "ERROR: Deployment did not finish in time"
      exit 1
  only:
    - main
```

#### 3. Deploying a tar archive from CI

If you build a `docker save` archive in the pipeline and want to upload it instead of pulling from a registry:

```bash
docker save -o myapp.tar myapp:${CI_COMMIT_SHORT_SHA}

curl -X POST "${SDP_URL}/api/v1/deployments" \
  -H "X-API-Key: ${SDP_API_KEY}" \
  -F "ssh_key=@-;type=application/octet-stream" <<< "${SSH_PRIVATE_KEY}" \
  -F "image_source=tar" \
  -F "docker_image=@myapp.tar" \
  -F "app_deploy_image_name=myapp:${CI_COMMIT_SHORT_SHA}" \
  -F "app_deploy_container_name=myapp" \
  -F "app_host_port=8080" \
  -F "app_container_port=80" \
  -F "ansible_host=${DEPLOY_HOST}" \
  -F "ansible_port=22" \
  -F "ansible_user=${DEPLOY_USER}"
```

#### Tips

- **SSE events**: instead of polling, you can connect to `GET /api/v1/deployments/<id>/events` to receive real-time deployment logs.
- **Multiple servers**: repeat `ansible_host`, `ansible_port`, `ansible_user` fields for each target server.
- **Trivy**: SDP scans the image for vulnerabilities before deployment. You can control the blocking threshold with the `trivy_fail_on` field (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`).
- **Dockerfile**: optionally attach `dockerfile=@Dockerfile` for Hadolint static analysis.

Deployments can send progress notifications (start / success / failure / critical error)
to a Telegram chat:

1. Create a bot via @BotFather and set its token in the environment:
   `TELEGRAM_BOT_TOKEN=<token>` (for Docker: `docker run -e TELEGRAM_BOT_TOKEN=... -p 8080:8080 -d f0ra1n/sdp`).
2. Find out your numeric chat id (for example, via @userinfobot).
3. Enter it into the «Telegram chat id» field of the main form (it is remembered in the
   browser via localStorage) or pass it as the `telegram_chat_id` form field to
   `POST /api/v1/deployments`.

Notifications are optional: if `TELEGRAM_BOT_TOKEN` is not set or the chat id is empty,
deployments run without them. The bot must be able to write to that chat
(the user has to start a conversation with the bot first).


2. Managed Node

- Created User with all privileges through sudo without using password (NOPASSWD: all) and with ssh_pub_key (you need to provide private key)  
- Installed Python3

