import subprocess
import os

edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
proto_path = r"D:\Bill\design\ui_prototype.html"
out_dir = r"D:\Bill\design\screenshots"
os.makedirs(out_dir, exist_ok=True)

with open(proto_path, "r", encoding="utf-8") as f:
    content = f.read()

themes = ["dark", "light"]
views = [
    ("purchase", "desktop-purchase"),
    ("supplier", "desktop-supplier"),
    ("bill", "koyambedu-bill"),
    ("registration", "shop-registration"),
    ("admin", "super-admin")
]

for theme in themes:
    for view_label, vkey in views:
        filename = f"screen_{theme}_{view_label}.png"
        trigger = f"""
        <script>
          document.addEventListener('DOMContentLoaded', function() {{
            setTheme('{theme}');
            switchView('{vkey}');
          }});
        </script>
        """
        temp_content = content.replace("</body>", trigger + "</body>")
        temp_html = os.path.join(out_dir, f"temp_{theme}_{vkey}.html")
        with open(temp_html, "w", encoding="utf-8") as tf:
            tf.write(temp_content)
        
        out_file = os.path.join(out_dir, filename)
        cmd = [
            edge,
            "--headless",
            "--disable-gpu",
            "--window-size=1280,1050",
            f"--screenshot={out_file}",
            f"file:///{temp_html.replace(os.sep, '/')}"
        ]
        subprocess.run(cmd, timeout=15)
        if os.path.exists(temp_html):
            os.remove(temp_html)
        print(f"Captured {filename}: {os.path.exists(out_file)}")

print("All dual-theme screenshots rendered successfully!")
