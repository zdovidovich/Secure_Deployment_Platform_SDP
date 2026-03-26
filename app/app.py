from flask import Flask, render_template, request
from libs.temp_files import save_temp_file, create_inventory_temp_file, cleanup_temp_files

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy():
    file_path_ssh_key = save_temp_file(request.files.get('ssh_key'), "ssh_key_")
    file_path_image = save_temp_file(request.files.get('docker_image'), "docker_image_")
    file_path_inventory = create_inventory_temp_file(request.form, file_path_ssh_key)    
    for i in request.form:
       print(i)
    cleanup_temp_files()
    return "Nothing yet"

# проверка загруженных параметров (docker image + priv_key, мб еще проверить остальные параметры (хотя некоторые уже проверяются в ansible))
# сделать inventory файл, добавить сам хост (имя - хэш(айпи:пользователь:время создания, ansible_host, ansible_user, ansible_private_key_file, ansible_port), загрузить priv_key для ssh)
# указать дополнительные переменные (ssh_port, app_image_path, app_image_name, app_container_name, app_ports, app_volumes?, app_envs?)  
# начать запускать роли в правильном порядке
# в прямом эфире показывать вывод терминала?
if __name__ == '__main__':
  app.run(debug=True, port=8080)