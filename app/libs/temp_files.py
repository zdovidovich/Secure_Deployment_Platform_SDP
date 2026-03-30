import os
import tempfile
import uuid
from werkzeug.utils import secure_filename
import glob
from libs.utils import get_project_root
from libs.ansible import get_base_dir_ansible

def get_base_dir():
    return os.path.dirname(os.path.abspath(__file__))

def save_temp_file(file_obj, prefix='upload_'):
    """
    Сохраняет загруженный файл во временную папку с уникальным именем.
    Возвращает путь к файлу.
    """
    original_filename = secure_filename(file_obj.filename)
    
    unique_name = f"{prefix}{uuid.uuid4().hex}_{original_filename}"
    
    temp_dir = tempfile.gettempdir() 

    file_path = os.path.join(temp_dir, unique_name)
    
    file_obj.save(file_path)
    
    os.chmod(file_path, 0o600)
    
    return file_path

def create_inventory_temp_file(ansible_params: dict, ssh_key_path) -> str:
    """
    Создаёт временный inventory файл для Ansible.
    Возвращает полный путь к файлу.
    """
    name = uuid.uuid4().hex[:8]  
    unique_name = f"inventory_{name}"
    
    inventory_dir = os.path.join(get_base_dir_ansible(), 'inventory')
    
    os.makedirs(inventory_dir, exist_ok=True)
    
    file_path = os.path.join(inventory_dir, unique_name)
    
    with open(file_path, 'w') as f:
        f.write("[server]\n")
        f.write(
            f"{name} "
            f"ansible_host={ansible_params['ansible_host']} "
            f"ansible_port={ansible_params['ansible_port']} "
            f"ansible_user={ansible_params['ansible_user']} "
            f"ansible_ssh_private_key_file={ssh_key_path} "
        )

    os.chmod(file_path, 0o600)
    
    return file_path

def cleanup_temp_files(prefixes=('ssh_key_', 'docker_image_', 'dockerfile_', 'inventory_')):
    temp_dir = tempfile.gettempdir()
    for prefix in prefixes:
        for file_path in glob.glob(os.path.join(temp_dir, f'{prefix}*')):
            try:
                os.remove(file_path)
            except OSError:
                pass  
    for file_path in glob.glob(os.path.join(os.path.join(get_project_root(),  'ansible', 'inventory'), f'inventory_*')):
        try:
            os.remove(file_path)
        except OSError:
            pass  
    
    