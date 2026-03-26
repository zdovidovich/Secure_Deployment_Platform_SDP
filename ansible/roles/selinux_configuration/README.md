Role Name
=========

This role enables/disables SELinux on RHEL-based systems and if enabled - implements all rules that were given

Requirements
------------

Role Variables
--------------

1.  selinux_state: string. Possible types: 'disabled', 'permissive', 'enforcing'. (default: enforcing) 
2.  selinux_rules: list [port, type]. (default: [])
    example: 
    selinux_rules:
      - type: ssh_port_t
        port: 22


Dependencies
------------

A list of other roles hosted on Galaxy should go here, plus any details in regards to parameters that may need to be set for other roles, or variables that are used from other roles.

Example Playbook
----------------

- name: Smth here
  include_role:
    name: selinux_configuration
  vars:
    selinux_state: 'enforcing'
    selinux_rules:
      - type: ssh_port_t
        port: 22


License
-------

BSD

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
