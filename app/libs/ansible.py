import ansible_runner
import os
from libs.utils import get_project_root


def get_base_dir_ansible():
    return os.path.join(get_project_root(), "..", 'ansible')


def run_check(file_path_inventory):
    result = ansible_runner.run(
        private_data_dir=get_base_dir_ansible(),
        inventory=file_path_inventory,
        module='ping',
        host_pattern='all'
    )
    return result


def run_full_configuring(extravars: dict, file_path_inventory):
    return run_playbook("configure.yml", extravars, file_path_inventory)


def run_playbook(playbook, extravars: dict, file_path_inventory):
    extravars.update({"ansible_become": "True"})
    result = ansible_runner.run(
        private_data_dir=get_base_dir_ansible(),
        inventory=file_path_inventory,
        playbook=os.path.join(get_base_dir_ansible(), playbook),
        host_pattern='all',
        extravars=extravars,
        envvars={
            "ANSIBLE_NOCOLOR": "true"
        }
    )
    return result


def run_role(role, extravars: dict, file_path_inventory):
    extravars.update({"ansible_become": "True"})
    result = ansible_runner.run(
        private_data_dir=get_base_dir_ansible(),
        inventory=file_path_inventory,
        role=role,
        host_pattern='all',
        extravars=extravars
    )
    return result.stdout.read()
