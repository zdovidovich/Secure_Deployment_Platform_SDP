import subprocess
import json
from typing import Optional, Union


def run_binary_scanner(
    binary_path: str,
    args: list,
    parse_json: bool = True,
) -> tuple[bool, Optional[Union[dict, str]], str]:
    """
    Запускает внешний бинарник и возвращает результат.

    Возвращает: (success, parsed_output_or_raw, stderr)
    """
    try:
        cmd = [binary_path] + args

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if parse_json and result.stdout.strip():
            try:
                return True, json.loads(result.stdout), result.stderr
            except json.JSONDecodeError:
                return False, result.stdout, "Failed to parse JSON output"

        return True, result.stdout, result.stderr

    except subprocess.CalledProcessError as e:
        return False, None, f"Command failed: {e.stderr}"
    except FileNotFoundError:
        return False, None, f"Binary not found: {binary_path}"
