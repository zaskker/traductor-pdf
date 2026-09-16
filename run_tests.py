import os
import tempfile
import sys
import getpass

getpass.getuser = lambda: "isolated"


if __name__ == "__main__":
    new_tmp = os.path.join(os.getcwd(), "temp_run_5")
    appdata_tmp = os.path.join(new_tmp, "appdata")
    pytest_tmp = os.path.join(new_tmp, "pytest_base")
    os.makedirs(appdata_tmp, exist_ok=True)
    os.makedirs(pytest_tmp, exist_ok=True)
    
    os.environ["TMP"] = new_tmp
    os.environ["TEMP"] = new_tmp
    os.environ["LOCALAPPDATA"] = appdata_tmp
    tempfile.tempdir = new_tmp
    
    import pytest
    
    args = sys.argv[1:] if len(sys.argv) > 1 else ["tests"]
    args.extend(["-q", f"--basetemp={pytest_tmp}", "--junitxml=recovery/pytest_report.xml"])
    sys.exit(pytest.main(args))
