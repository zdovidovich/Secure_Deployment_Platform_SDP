Role Name
=========

Run docker container with given image

Requirements
------------

Need to install community.docker collection:
ansible-galaxy collection install community.docker

Role Variables
--------------

1. app_image_path: docker image in tar archive. Use docker image save to save your image in tar archive 
2. app_image_name: name of the image
3. app_container_name: name of the container
4. app_ports: mapping ports (host:container)
5. app_envs: environment variables for container
6. app_volumes: attach volumes to container (host:container)
7. app_ro_fs: mount the container’s root file system as read-only
8. app_memory: memory limit
9. app_cpus: cpecify how much of the available CPU resources a container can use

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
      app_image_path: nginx.tar
      app_image_name: nginx
      app_container_name: nginx
      app_host_port: 80
      app_container_port: 80
      app_envs: {} 
      app_volumes: []

License
-------

BSD

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
