from flask import Flask, render_template, request
from libs.temp_files import save_temp_file, create_inventory_temp_file, cleanup_temp_files
from libs.ansible import run_full_configuring
from libs.validation import validate_all_data
import os
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy():
    file_path_ssh_key = save_temp_file(
        request.files.get('ssh_key'), "ssh_key_"
    )
    file_path_image = save_temp_file(
        request.files.get('docker_image'), "docker_image_"
    )
    
    is_valid, errors, validated_data = validate_all_data(request.form, file_path_image, file_path_ssh_key)

    if not is_valid:
        return {'status': 'error', 'errors': errors}, 400
    
    file_path_inventory = create_inventory_temp_file(
        {
            'ansible_host': validated_data['ansible_host'],
            'ansible_port': validated_data['ansible_port'],
            'ansible_user': validated_data['ansible_user']
        },
        file_path_ssh_key
    )
    
    extra_vars = {
        'ssh_port': validated_data['ssh_port'],
        'app_image_path': file_path_image,
        'selinux_state': "enforcing" if request.form.get('enable_selinux') == 'on' else "disabled",
        'fail2ban_state': True if request.form.get('enable_fail2ban') else False,
        'app_image_name': validated_data['app_image_name'],
        'app_container_name': validated_data['app_container_name'],
        'app_ports': [f"{validated_data['app_host_port']}:{validated_data['app_container_port']}"],
        'app_volumes': validated_data['app_volumes'],
        'app_envs': validated_data['app_envs'],
    }
    result = run_full_configuring(extra_vars, file_path_inventory)
    
    cleanup_temp_files()
    if result.failed:
        return {
            'status': 'error',
            'message': 'Ansible playbook failed',
            'errors': result.stderr.read(),
            'stats': result.stats
        }, 500
    
    return {
        'status': 'success',
        'message': 'Deployment completed',
        'stats': result.stats
    }, 200


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8080)
