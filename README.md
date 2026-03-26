# SDP (Secure Deployment Platform)

### Verified working on distros:

- Debian
- Ubuntu (Ubuntu Server)
- Rocky Linux
- Fedora (Fedora Server)
- CentOS

### Requirements

1. Master Node

- Ansible (core >= 2.20)  
- community.docker for ansible-galaxy

2. Managed Node

- Created User with all privileges through sudo without using password (NOPASSWD: all) and with ssh_pub_key (you need to provide private key)  
- Installed Python3
- docker image file saved using `docker image save`
