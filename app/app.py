from flask import Flask, render_template, request
from libs.temp_files import save_temp_file, create_inventory_temp_file, cleanup_temp_files
from libs.ansible import run_full_configuring
from libs.validation import validate_all_data
from libs.hadolint import scan_dockerfile,  format_hadolint_result
from libs.trivy import scan_image, format_trivy_result

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
    dockerfile = request.files.get('dockerfile')
    dockerfile_path = None

    if dockerfile and dockerfile.filename:
        dockerfile_path = save_temp_file(dockerfile, "dockerfile_")
        result_scan_dockerfile = scan_dockerfile(dockerfile_path)
        hadolint_result_code, hadolint_result_string = format_hadolint_result(result_scan_dockerfile['issues'])
        if hadolint_result_code:
            return {
            'status': 'error',
            'message': 'Hadolint Dockerfile checking failed',
            'hadolint_result': hadolint_result_string
        }, 500

    is_valid, errors, validated_data = validate_all_data(request.form, file_path_image, file_path_ssh_key)

    if not is_valid:
        return {'status': 'error', 'errors': errors}, 400
    
    result_scan_image = scan_image(file_path_image)
    if result_scan_image['success'] == False:
        return {
            'status': 'error',
            'message': 'Trivy image checking failed',
            'error': result_scan_image
        }, 500
    
    if result_scan_image['critical_count'] + result_scan_image['high_count'] > 0:
        return {
            'status': 'error',
            'message': 'Trivy image checking failed: High/Critical vulnerabilities were found',
            'error': format_trivy_result(result_scan_image['vulnerabilities'])
        }, 500

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
    if result.errored:
        return {
            'status': 'error',
            'message': 'Ansible playbook failed',
            'hadolint_result': hadolint_result_string,
            'errors': result.stderr.read(),
            'stats': result.stats
        }, 500
    
    return {
        'status': 'success',
        'message': 'Deployment completed',
        'hadolint_result': hadolint_result_string,
        'stats': result.stats
    }, 200


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8080)
