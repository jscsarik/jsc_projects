import os
import subprocess
import sys
import ctypes

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def restore_monitor():
    # Candidates for the installer path
    paths = [
        r"C:\정승찬\google-AI-studio\VirtualMonitor\deviceinstaller64.exe",
        r"C:\Users\정승찬\google-AI-studio\VirtualMonitor\deviceinstaller64.exe"
    ]

    installer_path = None
    for p in paths:
        if os.path.exists(p):
            installer_path = p
            break
    
    if not installer_path:
        print("Error: deviceinstaller64.exe not found in expected paths.")
        print(f"Checked: {paths}")
        return

    print(f"Found installer at: {installer_path}")
    
    # deviceinstaller64.exe enablevdd
    # must be run as admin
    if not is_admin():
        # Re-run the program with admin rights
        print("Requesting admin privileges...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        return

    try:
        print("Running enablevdd...")
        # deviceinstaller64.exe enablevdd
        result = subprocess.run([installer_path, "enablevdd"], check=True, capture_output=True, text=True)
        print("Output:", result.stdout)
        print("Success! Virtual monitor enabled.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to enable monitor. Error: {e}")
        print("Stderr:", e.stderr)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    restore_monitor()
