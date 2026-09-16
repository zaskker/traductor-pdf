import sys
import os
from pathlib import Path

def is_frozen() -> bool:
    """Returns True if the application is running as a PyInstaller frozen executable."""
    return getattr(sys, "frozen", False)

def get_base_path() -> Path:
    """
    Returns the base path for application resources (fonts, icons, templates).
    In frozen mode, this is the directory containing the executable or _MEIPASS.
    In development, it's the root of the repository.
    """
    if is_frozen():
        return Path(sys._MEIPASS)
    else:
        return Path(__file__).parent.parent.parent

def get_app_data_path() -> Path:
    """
    Returns the path to the user's Local AppData directory for persistent data.
    This ensures SQLite DB and logs survive updates and are kept out of the bundle.
    """
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        # Fallback to user home if LOCALAPPDATA is somehow missing
        local_app_data = Path.home() / "AppData" / "Local"
    
    app_data_path = Path(local_app_data) / "TraductorPDF"
    app_data_path.mkdir(parents=True, exist_ok=True)
    return app_data_path

def get_logs_path() -> Path:
    """Returns the path where application logs should be written."""
    logs_path = get_app_data_path() / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    return logs_path

def get_db_path() -> Path:
    """Returns the absolute path to the main SQLite database."""
    return get_app_data_path() / "traductor.sqlite"
