import os

def get_project_root():
    """Возвращает корень проекта (где лежит app.py)"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
