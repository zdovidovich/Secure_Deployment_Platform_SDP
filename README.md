# SDP (Secure Deployment Platform)

## Why do you need it?

SDP (Secure Deployment Platform) is a platform for automated Docker containers deployment with security practices. 

Key features:
- Secure infrastructure: Automatic configuration of SSH, Firewall, Fail2Ban, and SELinux on the target host.
- Vulnerability checking: Docker image scanning via Trivy and Dockerfile static analysis via Hadolint.
- Full automation: Docker Engine installation and container deployment with configurable parameters (ports, volumes, environment variables, resource limits).

Result: Your application runs in a secure environment without the need for in-depth knowledge of Linux administration.

## Verified working on distros:

- Ubuntu (Ubuntu Server 24.04.4 LTS)
- Debian (12)
- RHEL (Rocky Linux 10.1)
- CentOS (10)
- Fedora (Fedora Server 43)

## Requirements

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


2. Managed Node

- Created User with all privileges through sudo without using password (NOPASSWD: all) and with ssh_pub_key (you need to provide private key)  
- Installed Python3

