import winreg
import subprocess

def check_search_service():
    try:
        res = subprocess.run(["powershell", "-Command", "Get-Service -Name WSearch"], capture_output=True, text=True)
        print("WSearch Service Status:")
        print(res.stdout)
    except Exception as e:
        print("Error checking service:", e)

def check_registry():
    try:
        # Check if .txt has persistent handler
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r".txt") as key:
            try:
                val, t = winreg.QueryValueEx(key, "")
                print(f"ROOT .txt default value: {val}")
            except Exception:
                pass
        
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r".txt\PersistentHandler") as key:
            val, t = winreg.QueryValueEx(key, "")
            print(f"PersistentHandler for .txt: {val}")
    except Exception as e:
        print("Error reading registry:", e)

check_search_service()
check_registry()
