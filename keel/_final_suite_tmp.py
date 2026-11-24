import os, sys, pytest
home = r"C:\Users\Admin\AppData\Local\Temp\opencode\cleanhome2"
os.makedirs(home, exist_ok=True)
os.environ["HOME"] = home
os.environ["USERPROFILE"] = home
sys.path.insert(0, "src")
raise SystemExit(pytest.main(["-v", "-o", "faulthandler_timeout=120"]))
