import mss
import platform
import sys

print(f"Platform: {platform.system()} {platform.release()}")

try:
    with mss.mss() as sct:
        print(f"Monitors: {len(sct.monitors)}")
        for i, m in enumerate(sct.monitors):
            print(f"Monitor {i}: {m}")
            
    if len(sct.monitors) > 3:
        print("RESULT: Virtual Monitor Index 3 Found!")
    else:
        print("RESULT: Virtual Monitor Missing (Expected index 3)")

except Exception as e:
    print(f"Error checking monitors: {e}")
