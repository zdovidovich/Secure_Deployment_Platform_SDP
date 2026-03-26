from flask import Flask, render_template, request
from libs.temp_files import save_temp_file, create_inventory_temp_file, cleanup_temp_files
from libs.ansible import run_role

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/deploy', methods=['POST'])
def deploy():
    file_path_ssh_key = save_temp_file(
        request.files.get('ssh_key'), "ssh_key_")
    file_path_image = save_temp_file(
        request.files.get('docker_image'), "docker_image_")
    file_path_inventory = create_inventory_temp_file(
        request.form, file_path_ssh_key)
    extra_vars = {'ssh_port': int(request.form['ssh_port']), 'app_image_path': file_path_image, 'selinux_state': "enforcing" if request.form['enable_selinux'] == 'on' else "disabled",
                  'app_image_name': request.form['app_image_name'], 'app_container_name': request.form['app_container_name'], 'app_ports': f"{request.form['app_host_port']}:{request.form['app_container_port']}", 'app_volumes': request.form['app_volumes'], 'app_envs': request.form['app_envs']}
    print(extra_vars)
    run_role('ssh_hardening', extra_vars, file_path_inventory)
    cleanup_temp_files()
    return "Nothing yet"


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8080)
