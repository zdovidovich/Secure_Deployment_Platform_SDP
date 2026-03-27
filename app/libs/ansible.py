import ansible_runner
import json
from libs.temp_files import get_base_dir
import os
from utils import get_project_root


PLAYBOOKS_DIR="playbooks"
ROLES_DIR="roles"

def get_base_dir_ansible():
    return os.path.join(get_project_root(), 'ansible')

def run_check(file_path_inventory):
    result = ansible_runner.run(
    private_data_dir= get_base_dir_ansible(),
    inventory=file_path_inventory,
    module='ping',
    host_pattern='all'
)
    print(result.stdout.read())
    print(json.dumps(result.stats, indent=4))

def run_full_configuring(extravars: dict, file_path_inventory):
    return run_playbook("configure.yml", extravars, file_path_inventory)

def run_playbook(playbook, extravars: dict, file_path_inventory):
    extravars.update({"ansible_become": "True"})
    result = ansible_runner.run(
    private_data_dir= get_base_dir_ansible(),
    inventory=file_path_inventory,
    playbook=os.path.join(get_base_dir_ansible(), PLAYBOOKS_DIR, playbook),
    host_pattern='all',
    extravars=extravars
)
    return result


def run_role(role, extravars: dict, file_path_inventory):
    extravars.update({"ansible_become": "True"})
    result = ansible_runner.run(
    private_data_dir= get_base_dir_ansible(),
    inventory=file_path_inventory,
    role=role,
    host_pattern='all',
    extravars=extravars
)
    return result.stdout.read()

