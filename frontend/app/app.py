from flask import Flask, render_template, request, redirect, url_for, jsonify
import requests
import json
import os

API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000/api/v1')

app = Flask(__name__)


@app.route('/')
def index():
    """Главная страница с формой деплоя"""
    return render_template('index.html')


@app.route('/deploy', methods=['GET'])
def deploy_form():
    """Страница формы деплоя"""
    return render_template('deploy_form.html')


@app.route('/deploy', methods=['POST'])
def create_deployment():
    """Создание деплоя через API"""
    try:
        # Сбор данных формы
        data = {
            'ansible_host': request.form.get('ansible_host'),
            'ansible_port': int(request.form.get('ansible_port', 22)),
            'ansible_user': request.form.get('ansible_user'),
            'app_deploy_image_name': request.form.get('app_deploy_image_name'),
            'app_deploy_container_name': request.form.get('app_deploy_container_name'),
            'app_host_port': int(request.form.get('app_host_port')),
            'app_container_port': int(request.form.get('app_container_port')),
            'enable_trivy': request.form.get('enable_trivy') == 'on',
            'trivy_fail_on': request.form.get('trivy_fail_on', 'HIGH'),
            'enable_selinux': request.form.get('enable_selinux') == 'on',
            'enable_fail2ban_for_ssh': request.form.get('enable_fail2ban_for_ssh') == 'on',
            'ssh_hardening_disable_pass': request.form.get('ssh_hardening_disable_pass') == 'on',
            'app_deploy_ro_fs': request.form.get('app_deploy_ro_fs') == 'on',
            'enable_container_fail2ban': request.form.get('enable_container_fail2ban') == 'on',
        }
        
        # Файлы
        files = {
            'ssh_key': request.files['ssh_key'],
            'docker_image': request.files['docker_image'],
        }
        
        if 'dockerfile' in request.files and request.files['dockerfile'].filename:
            files['dockerfile'] = request.files['dockerfile']
        
        # Отправка на API
        response = requests.post(f'{API_BASE_URL}/deployments/', data=data, files=files)
        response.raise_for_status()
        
        deployment = response.json()
        deployment_id = deployment['id']
        
        return redirect(url_for('deployment_status', deployment_id=deployment_id))
    
    except requests.exceptions.RequestException as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/deploy/<deployment_id>')
def deployment_status(deployment_id):
    """Страница статуса деплоя"""
    try:
        response = requests.get(f'{API_BASE_URL}/deployments/{deployment_id}')
        response.raise_for_status()
        deployment = response.json()
        return render_template('deployment_status.html', deployment=deployment)
    except requests.exceptions.RequestException as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/api/deployments')
def api_deployments():
    """API endpoint для получения списка деплоев (для фронтенда)"""
    try:
        response = requests.get(f'{API_BASE_URL}/deployments/')
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
