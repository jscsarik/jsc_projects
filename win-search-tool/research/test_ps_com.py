import subprocess
cmd = '$sm = New-Object -ComObject "Search.SearchManager"; echo $sm'
res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)
