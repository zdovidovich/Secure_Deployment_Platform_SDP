from .scanner_base import run_binary_scanner
import os

TRIVY_PATH = os.getenv("TRIVY_PATH", "trivy")


def scan_image(image_path: str, fail_on_severity: str = "HIGH") -> dict:
    """
    Запускает Trivy для сканирования Docker-образа.

    Args:
        image_path: Путь к образу (.tar файл)
        fail_on_severity: Порог блокировки ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE')

    Returns:
        dict с результатами сканирования и решением о блокировке
    """
    SEVERITY_ORDER = ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

    success, output, error = run_binary_scanner(
        binary_path=TRIVY_PATH,
        args=[
            "image",
            "--input",
            image_path,
            "--format",
            "json",
            "--exit-code",
            "0",
            "--no-progress",
        ],
        parse_json=True,
    )

    if not success:
        return {
            "success": False,
            "vulnerabilities": [],
            "blocked": False,
            "error": error,
        }

    vulnerabilities = []
    if isinstance(output, dict) and "Results" in output:
        for result in output["Results"]:
            if "Vulnerabilities" in result:
                vulnerabilities.extend(result["Vulnerabilities"])

    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}

    for vuln in vulnerabilities:
        sev = vuln.get("Severity", "UNKNOWN").upper()
        if sev in severity_counts:
            severity_counts[sev] += 1

    blocked = False
    blocking_count = 0
    blocking_severity = None

    if fail_on_severity and fail_on_severity != "NONE":
        try:
            fail_index = SEVERITY_ORDER.index(fail_on_severity.upper())
        except ValueError:
            fail_index = SEVERITY_ORDER.index("HIGH")

        for i in range(fail_index, len(SEVERITY_ORDER)):
            level = SEVERITY_ORDER[i]
            blocking_count += severity_counts.get(level, 0)

        if blocking_count > 0:
            blocked = True
            blocking_severity = fail_on_severity.upper()

    return {
        "success": True,
        "vulnerabilities": vulnerabilities,
        "blocked": blocked,
        "blocking_count": blocking_count,
        "blocking_severity": blocking_severity,
        "severity_counts": severity_counts,
        "critical_count": severity_counts["CRITICAL"],
        "high_count": severity_counts["HIGH"],
        "medium_count": severity_counts["MEDIUM"],
        "low_count": severity_counts["LOW"],
        "error": None,
    }


def format_trivy_result(scan_data: dict | list) -> str:
    """
    Форматирует вывод Trivy в читаемую строку.

    Args:
        scan_data: Словарь с результатами сканирования (как возвращает Trivy --format json)
                   или список уязвимостей

    Returns:
        Красиво отформатированная строка с результатами проверки
    """
    vulnerabilities = []

    if isinstance(scan_data, list):
        vulnerabilities = scan_data
    elif isinstance(scan_data, dict):
        if "Results" in scan_data:
            for result in scan_data["Results"]:
                if "Vulnerabilities" in result:
                    vulnerabilities.extend(result["Vulnerabilities"])
        elif "Vulnerabilities" in scan_data:
            vulnerabilities = scan_data["Vulnerabilities"]

    if not vulnerabilities:
        return "Trivy: уязвимости не обнаружены"

    severity_config = {
        "CRITICAL": {"label": "CRITICAL", "order": 0},
        "HIGH": {"label": "HIGH", "order": 1},
        "MEDIUM": {"label": "MEDIUM", "order": 2},
        "LOW": {"label": "LOW", "order": 3},
        "UNKNOWN": {"label": "UNKNOWN", "order": 4},
    }

    grouped = {level: [] for level in severity_config}

    for vuln in vulnerabilities:
        severity = vuln.get("Severity", "UNKNOWN").upper()
        if severity in grouped:
            grouped[severity].append(vuln)
        else:
            grouped["UNKNOWN"].append(vuln)

    output_lines = []
    output_lines.append("Результаты сканирования Trivy:")
    output_lines.append("=" * 60)

    total = len(vulnerabilities)
    output_lines.append(f"Всего найдено: {total} уязвимость(ей)")

    stats = []
    for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]:
        count = len(grouped[level])
        if count > 0:
            stats.append(f"{severity_config[level]['label']}: {count}")

    if stats:
        output_lines.append(f"({', '.join(stats)})")
        output_lines.append("")

    for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]:
        items = grouped[level]
        if not items:
            continue

        config = severity_config[level]
        level_name = config["label"]

        output_lines.append(f"\n{level_name} ({len(items)}):")
        output_lines.append("-" * 55)

        for i, vuln in enumerate(items, 1):
            cve_id = vuln.get("VulnerabilityID", "UNKNOWN")
            pkg_name = vuln.get("PkgName", "unknown")
            installed_ver = vuln.get("InstalledVersion", "?")
            fixed_ver = vuln.get("FixedVersion", "Not fixed")
            title = vuln.get("Title", "No title")
            description = vuln.get("Description", "No description")
            cvss_score = vuln.get("CVSS", {}).get("nvd", {}).get("V3Score", "N/A")
            primary_url = vuln.get("PrimaryURL", "")

            if len(description) > 200:
                description = description[:197] + "..."

            vuln_str = (
                f"  {i}. [{cve_id}] {pkg_name} ({installed_ver} → {fixed_ver})\n"
                f"     {title}\n"
                f"     CVSS: {cvss_score} | {primary_url}\n"
                f"     {description}"
            )
            output_lines.append(vuln_str)
            output_lines.append("")

    output_lines.append("=" * 60)

    critical_count = len(grouped["CRITICAL"])
    high_count = len(grouped["HIGH"])

    if critical_count > 0 or high_count > 0:
        output_lines.append("")
        output_lines.append("Рекомендации:")
        if critical_count > 0:
            output_lines.append(
                f"   • Срочно обновите пакеты с {critical_count} CRITICAL уязвимостями"
            )
        if high_count > 0:
            output_lines.append(
                f"   • Запланируйте обновление для {high_count} HIGH уязвимостей"
            )

    return "\n".join(output_lines)
