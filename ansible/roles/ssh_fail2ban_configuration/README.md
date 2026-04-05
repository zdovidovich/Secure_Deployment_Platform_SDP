Role Name
=========

Installs fail2ban if not installed and configures it for sshd and recidive. 

Requirements
------------

Any pre-requisites that may not be covered by Ansible itself or the role should be mentioned here. For instance, if the role uses the EC2 module, it may be a good idea to mention in this section that the boto package is required.

Role Variables
--------------

1. ssh_port: port which listens sshd (default: 22)
2. log_ssh_path: path to log file sshd (default: /var/log/auth.log)

Dependencies
------------

roles/fail2ban_install

Example Playbook
----------------

- name: Configure fail2ban for sshd and recidive
  include_role:
    name: ssh_fail2ban_configuration
  vars:
    ssh_port: 8081
    log_ssh_path: /var/log/access.log

License
-------

BSD

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
