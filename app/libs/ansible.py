import ansible_runner
import json
from libs.temp_files import get_base_dir
import os

def get_base_dir_ansible():
    return os.path.join(get_base_dir(), '..', '..', 'ansible')

def run_check(file_path_inventory):
    result = ansible_runner.run(
    private_data_dir= get_base_dir_ansible(),
    inventory=file_path_inventory,
    module='ping',
    host_pattern='all'
)
    print(result.stdout.read())
    print(json.dumps(result.stats, indent=4))


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