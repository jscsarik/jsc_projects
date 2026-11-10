import winreg

def read_search_roots():
    path = r"SOFTWARE\Microsoft\Windows Search\CrawlScopeManager\Windows\SystemIndex\SearchRoots"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                    print(f"Search Root: {name}")
                    with winreg.OpenKey(key, name) as subkey:
                        j = 0
                        while True:
                            try:
                                val_name, val_data, val_type = winreg.EnumValue(subkey, j)
                                print(f"  {val_name} = {val_data}")
                                j += 1
                            except OSError:
                                break
                    i += 1
                except OSError:
                    break
    except Exception as e:
        print("Error:", e)

read_search_roots()
