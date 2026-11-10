Role Name
=========

Run docker container with given image

Requirements
------------

Need to install community.docker collection:
ansible-galaxy collection install community.docker

Role Variables
--------------

1. app_deploy_image_path: docker image in tar archive. Use docker image save to save your image in tar archive (required when docker_image_source=tar)
2. app_deploy_image_name: name of the image (e.g. nginx:latest or docker.io/nginx:latest)
3. app_deploy_container_name: name of the container
4. app_deploy_ports: mapping ports (host:container)
5. app_deploy_envs: environment variables for container
6. app_deploy_volumes: attach volumes to container (host:container)
7. app_deploy_ro_fs: mount the container’s root file system as read-only
8. app_deploy_memory: memory limit
9. app_deploy_cpus: specify how much of the available CPU resources a container can use
10. docker_image_source: source of the image - "tar" (upload archive) or "registry" (pull from registry). Default: "tar"
11. registry_url: Docker registry URL (e.g. docker.io, ghcr.io). Required when docker_image_source=registry
12. registry_username: registry username (optional, for private registries)
13. registry_password: registry password (optional, for private registries)

Default values for this role are empty

Dependencies
------------

role/docker_install

Example Playbook
----------------
-
 name: Deploy app
    include_role:
      name: app_deploy
    vars:
      app_deploy_image_path: nginx.tar
      app_deploy_image_name: nginx
      app_deploy_container_name: nginx
      app_deploy_host_port: 80
      app_deploy_container_port: 80
      app_deploy_envs: {} 
      app_deploy_volumes: []

License
-------

BSD

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
