from src.application.dtos.export import PreflightIssue, PreflightIssueCode, PreflightSeverity

# Mappings for Preflight Issues to user-friendly messages
_ISSUE_MESSAGES = {
    PreflightIssueCode.PROJECT_LOCKED: "El PDF original cambió desde que se creó el proyecto.",
    PreflightIssueCode.FINGERPRINT_MISMATCH: "El archivo PDF no coincide con el proyecto actual.",
    PreflightIssueCode.SOURCE_MISSING: "No se encuentra el archivo PDF original.",
    PreflightIssueCode.PAGE_COUNT_MISMATCH: "La cantidad de páginas del PDF original ha cambiado.",
    PreflightIssueCode.ENCRYPTED_SOURCE: "El archivo PDF está encriptado o protegido.",
    PreflightIssueCode.SIGNED_SOURCE: "El archivo PDF tiene firmas digitales.",
    PreflightIssueCode.INVALID_REGION_STATUS: "Hay regiones en un estado no exportable.",
    PreflightIssueCode.NO_EXPORTABLE_REGIONS: "No hay ninguna región para exportar.",
    PreflightIssueCode.PENDING_REGIONS: "Hay regiones todavía sin traducir.",
    PreflightIssueCode.INVALID_PAGE_NUMBER: "Hay regiones asignadas a páginas que no existen.",
    PreflightIssueCode.OVERFLOW: "Hay regiones cuya traducción no entra dentro del espacio disponible.",
    PreflightIssueCode.UNKNOWN_BACKGROUND: "No se pudo determinar con seguridad el fondo de algunas regiones.",
    PreflightIssueCode.COMPLEX_BACKGROUND: "Algunas regiones tienen un fondo complejo y todavía no pueden exportarse automáticamente.",
    PreflightIssueCode.OVERLAP: "Hay regiones traducidas que se superponen entre sí.",
}


def map_preflight_issues(issues: tuple[PreflightIssue, ...]) -> str:
    """
    Groups and maps PreflightIssues to a human-readable summary.
    Groups by issue_code, showing counts and optionally pages.
    """
    if not issues:
        return ""

    grouped_issues = {}
    for issue in issues:
        if issue.severity != PreflightSeverity.BLOCKER:
            continue

        if issue.code not in grouped_issues:
            grouped_issues[issue.code] = []
        grouped_issues[issue.code].append(issue)

    lines = []

    # We want to put PENDING_REGIONS at the end if present, or just sort them
    for code, group in sorted(grouped_issues.items(), key=lambda x: x[0].value):
        msg = _ISSUE_MESSAGES.get(code, f"Error desconocido ({code.name})")

        count = len(group)
        pages = sorted(list(set(i.page_number for i in group if i.page_number)))

        if count > 1:
            line = f"• {msg} ({count} regiones afectadas)"
        else:
            line = f"• {msg}"

        if pages:
            if len(pages) <= 3:
                pages_str = ", ".join(str(p) for p in pages)
                line += f" (Páginas: {pages_str})"
            else:
                line += f" (En {len(pages)} páginas)"

        lines.append(line)

    return "\n".join(lines)


def map_export_error(error_code: str) -> str:
    """Maps worker/controller export error codes to human-readable text."""
    mapping = {
        "INVALID_REQUEST": "La solicitud de exportación es inválida o tiene datos incorrectos.",
        "SOURCE_FINGERPRINT_MISMATCH": "El PDF original cambió desde que preparaste el proyecto. Deberás reabrir/revalidar el proyecto.",
        "VALIDATION_FAILED": "Falló la validación interna durante la exportación.",
        "FILE_IO_ERROR": "No se pudo escribir el archivo de destino. Comprobá que no esté abierto en otro programa y que tengas permisos de escritura.",
        "EXPORT_ERROR": "Ocurrió un error inesperado al procesar el PDF.",
        "PROTOCOL_ERROR": "Error de comunicación con el proceso de exportación.",
        "UNKNOWN_EXPORT_ERROR": "Error desconocido durante la exportación.",
        "PROCESS_CRASHED": "El proceso de exportación se cerró inesperadamente.",
    }
    return mapping.get(error_code, f"Error en la exportación: {error_code}")
