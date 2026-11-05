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

`docker pull f0ra1n/sdp`

`docker run -p {your_host_port}:8080 -d f0ra1n/sdp ` 

Install directly on your pc:

Requirements:

- only Linux
- python3
- Ansible (tested on core == 2.20)
- git 
- trivy
- hadolint
- community.docker for ansible-galaxy (`ansible-galaxy collection install community.docker`)

`git clone https://github.com/zdovidovich/Secure_Deployment_Platform_SDP.git`

`cd Secure_Deployment_Platform_SDP`

`python3 -m venv .venv`

`.venv/bin/pip install -r app/requirements.txt`

`.venv/bin/python3 ./app/app.py`

### API

The application now exposes a lightweight HTTP API from the same monolith.

- `GET /api/v1/health` - healthcheck
- `POST /api/v1/deployments` - start deployment
- `GET /api/v1/deployments/<deployment_id>` - get deployment status/result
- `GET /api/v1/deployments/<deployment_id>/events` - stream deployment logs over SSE

`POST /api/v1/deployments` expects `multipart/form-data` with the same fields as the web form and these required files:

- `ssh_key`
- `docker_image`

Optional:

- `dockerfile`

If `SDP_API_KEY` is set in the environment, API requests must include header `X-API-Key: <value>`.

### Telegram notifications

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

