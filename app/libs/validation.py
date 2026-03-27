import re
from typing import Dict, Any, List, Tuple, Optional
import tarfile

class ValidationRule:
    """Класс правила валидации"""
    def __init__(self, pattern: str, error_msg: str, required: bool = True, to_int: bool = False):
        self.pattern = re.compile(pattern)
        self.error_msg = error_msg
        self.required = required
        self.to_int = to_int
    
    def validate(self, value: str) -> Tuple[bool, Optional[Any]]:
        if not value or value.strip() == '':
            if self.required:
                return False, None
            return True, None
        
        if self.to_int:
            try:
                value = int(value)
            except ValueError:
                return False, None
        
        if not self.to_int and not self.pattern.match(str(value)):
            return False, None
        
        return True, value


DEPLOY_FORM_RULES: Dict[str, ValidationRule] = {
    'ansible_host': ValidationRule(
        pattern=r'^(\d{1,3}\.){3}\d{1,3}$',
        error_msg='Неверный формат IP адреса',
        required=True
    ),
    'ansible_port': ValidationRule(
        pattern=r'^\d+$',
        error_msg='Порт должен быть числом',
        required=True,
        to_int=True
    ),
    'ssh_port': ValidationRule(
        pattern=r'^\d+$',
        error_msg='SSH порт должен быть числом',
        required=True,
        to_int=True
    ),
    'app_host_port': ValidationRule(
        pattern=r'^\d+$',
        error_msg='Порт хоста должен быть числом',
        required=True,
        to_int=True
    ),
    'app_container_port': ValidationRule(
        pattern=r'^\d+$',
        error_msg='Порт контейнера должен быть числом',
        required=True,
        to_int=True
    ),
    
    'ansible_user': ValidationRule(
        pattern=r'^[a-zA-Z][a-zA-Z0-9_-]*$',
        error_msg='Имя пользователя должно начинаться с буквы и содержать только буквы, цифры, _ и -',
        required=True
    ),
    'app_container_name': ValidationRule(
        pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$',
        error_msg='Неверный формат имени контейнера',
        required=True
    ),
    'app_image_name': ValidationRule(
        pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.:/-]*$',
        error_msg='Неверный формат имени образа',
        required=True
    ),
    
    'app_volumes': ValidationRule(
        pattern=r'^.*:.*$',
        error_msg='Volume должен быть в формате host:container',
        required=False
    ),
    'app_envs': ValidationRule(
        pattern=r'^[A-Za-z_][A-Za-z0-9_]*=.*$',
        error_msg='Переменная окружения должна быть в формате KEY=value',
        required=False
    ),
}

def validate_all_data(form_data: dict, file_path_image, file_path_private_ssh_key):
    result = validate_form_data(form_data)
    result_tar = validate_tar_archive(file_path_image)
    if not result_tar:
        result = (False, result[-1].append("Bad docker image"))
    result_ssh_key = validate_ssh_private_key(file_path_private_ssh_key)
    if not result_ssh_key:
        result = (False, result[-1].append("Bad private key ssh"))
    return result

def validate_form_data(form_data: dict) -> Tuple[bool, List[str]]:
    """
    Валидирует данные формы по правилам.
    Возвращает (success, errors_list)
    """
    errors = []
    validated_data = {}
    
    for field_name, rule in DEPLOY_FORM_RULES.items():
        value_str = form_data.get(field_name, '')
        
        is_valid, processed_value = rule.validate(value_str)
        
        if not is_valid:
            errors.append(f"{field_name}: {rule.error_msg}")
        elif processed_value is not None:
            validated_data[field_name] = processed_value
    
    if 'app_host_port' in validated_data and 'app_container_port' in validated_data:
        if not (0 < validated_data['app_host_port'] <= 65535):
            errors.append('app_host_port: Должен быть в диапазоне 1-65535')
        if not (0 < validated_data['app_container_port'] <= 65535):
            errors.append('app_container_port: Должен быть в диапазоне 1-65535')
    
    return len(errors) == 0, errors


def validate_tar_archive(file_path_image):
    try:
        with tarfile.open(file_path_image) as tar:
            tar.getnames() 
        return True
    except tarfile.ReadError:
        return False
    except tarfile.CompressionError:
        return False
    except FileNotFoundError:
        return False
    
def validate_ssh_private_key(file_path: str) -> bool:
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        if len(lines) < 2:
            return False
        
        first_line = lines[0].strip()
        last_line = lines[-1].strip()
        
        begin_pattern = r'^-----BEGIN\s+(?:OPENSSH\s+)?PRIVATE\s+KEY-----$'
        if not re.match(begin_pattern, first_line):
            return False
    
        end_pattern = r'^-----END\s+(?:OPENSSH\s+)?PRIVATE\s+KEY-----$'
        if not re.match(end_pattern, last_line):
            return False
        
        return True
        
    except (IOError, UnicodeDecodeError):
        return False