from .scanner_base import run_binary_scanner
import os

HADOLINT_PATH = os.getenv('HADOLINT_PATH', 'hadolint')

def scan_dockerfile(file_path: str, format: str = 'json') -> dict:
    """
    Запускает Hadolint для Dockerfile.
    Возвращает: {'success': bool, 'issues': list, 'error': str|None}
    """
    success, output, error = run_binary_scanner(
        binary_path=HADOLINT_PATH,
        args=[file_path, '--format', format],
        parse_json=(format == 'json')
    )
    if not success:
        return {'success': False, 'issues': [], 'error': error}
    
    issues = output if isinstance(output, list) else []
    
    errors = [issue for issue in issues if issue.get('level') == 'error']
    
    return {
        'success': True,
        'issues': issues,
        'errors': errors,
        'error': None
    }

def format_hadolint_result(issues: list | dict) -> str:
    """
    Форматирует вывод Hadolint в читаемую строку.
    
    Args:
        issues: Список словарей с проблемами или один словарь
        
    Returns:
        Красиво отформатированная строка с результатами проверки
    """
    if isinstance(issues, dict):
        issues = [issues]
    
    if not issues:
        return "Hadolint: проблем не обнаружено"
    
    result_code = 0

    level_labels = {
        'error': 'ERROR',
        'warning': 'WARNING',
        'info': 'INFO',
        'style': 'STYLE'
    }
    
    grouped = {
        'error': [],
        'warning': [],
        'info': [],
        'style': []
    }
    

    for issue in issues:
        level = issue.get('level', 'info')
        if issue == 'error':
            result_code = 1
        if level in grouped:
            grouped[level].append(issue)
        else:
            grouped['info'].append(issue)
    
    output_lines = []
    output_lines.append("Результаты проверки Hadolint:")
    output_lines.append("=" * 50)
    
    total = len(issues)
    output_lines.append(f"Всего найдено: {total} проблем(ы)")
    
    stats = []
    for level, items in grouped.items():
        if items:
            stats.append(f"{level_labels.get(level, level.upper())}: {len(items)}")
    if stats:
        output_lines.append(f"({', '.join(stats)})")
        output_lines.append("")
    
    for level in ['error', 'warning', 'info', 'style']:
        items = grouped[level]
        if not items:
            continue
        
        level_name = level_labels.get(level, level.upper())
        
        output_lines.append(f"\n{level_name} ({len(items)}):")
        output_lines.append("-" * 40)
        
        for i, issue in enumerate(items, 1):
            file_path = issue.get('file', 'unknown')
            line = issue.get('line', '?')
            column = issue.get('column', '?')
            code = issue.get('code', 'UNKNOWN')
            message = issue.get('message', 'No message')
            
            issue_str = (
                f"  {i}. [{code}] {file_path}:{line}:{column}\n"
                f"     {message}"
            )
            output_lines.append(issue_str)
    
    output_lines.append("")
    output_lines.append("=" * 50)
    
    return result_code, "\n".join(output_lines)