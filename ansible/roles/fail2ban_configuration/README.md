Role Name
=========

Installs fail2ban if not installed and configures it for custom service. 

Requirements
------------

Any pre-requisites that may not be covered by Ansible itself or the role should be mentioned here. For instance, if the role uses the EC2 module, it may be a good idea to mention in this section that the boto package is required.

Role Variables
--------------



1. app_log_path: path to log file, that fail2ban will read. Will create it if not exists (default: /var/log/nginx/access.log)
2. app_fail2ban_filter: name of the filter (default: filter)
3. app_fail2ban_regex: regex for the filter  (!\<HOST> is required here. Otherwise fail2ban won't work!) (default: "^/<HOST> bad pass$")
4. app_fail2ban_maxretry (default: 5)
5. app_fail2ban_bantime (seconds) (default: 3600)
6. app_fail2ban_findtime (seconds) (default: 600)
7. app_fail2ban_ports: ports, that will be in jail.local (default: 80,443)


Dependencies
------------

roles/fail2ban_install

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

- name: Smth here
  include_role:
    name: fail2ban_configuration
  vars:
    app_log_path: /var/log/nginx/access.log
    app_fail2ban_filter: custom
    app_fail2ban_regex: "^\<HOST>$"
    app_fail2ban_maxretry: 5
    app_fail2ban_bantime: 3600
    app_fail2ban_findtime: 600
    app_fail2ban_ports: 80,443

License
-------

BSD

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
