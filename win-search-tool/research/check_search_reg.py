import winreg

def print_registry_tree(key_path, depth=0):
    if depth > 3:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            # Print subkeys
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    full_path = f"{key_path}\\{subkey_name}"
                    print("  " * depth + f"- {subkey_name}")
                    print_registry_tree(full_path, depth + 1)
                    i += 1
                except OSError:
                    break
    except Exception as e:
        print("  " * depth + f"Error accessing {key_path}: {e}")

print_registry_tree(r"SOFTWARE\Microsoft\Windows Search")
