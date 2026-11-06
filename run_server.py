#!/usr/bin/env python
"""
AVT - FLOWER MERCHANT & COMMISSION AGENT
Portable Application Server Runner (Development & Production)
Launches Django monolith with Google Sheets Backend & Local Mirror
"""

import os
import sys
import argparse
import platform

def main():
    parser = argparse.ArgumentParser(description="AVT Flower Merchant Web Server Launcher")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Host IP to bind (default: 127.0.0.1)")
    parser.add_argument("--port", default=os.environ.get("PORT", "8002"), help="Port to bind (default: 8002)")
    parser.add_argument("--prod", action="store_true", help="Launch in production WSGI server mode (Waitress on Windows, Gunicorn on Linux)")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.shops.models import Shop
    from apps.parties.models import Supplier

    banner = f"""
====================================================================
  AVT – FLOWER MERCHANT & COMMISSION AGENT MANAGEMENT SYSTEM
  Kamarajar Flower Market, Koyambedu, Chennai-92
====================================================================
  * Mode             : {'PRODUCTION (WSGI Hardened)' if args.prod else 'DEVELOPMENT (Auto-Reloading)'}
  * Database Engine  : Django ORM (SQLite / PostgreSQL)
  * Active Shops     : {Shop.objects.count()}
  * Active Suppliers : {Supplier.objects.count()}
  * Server Endpoint  : http://{args.host}:{args.port}/
--------------------------------------------------------------------
  System Navigation Routes:
  1. Diagnostic Health  : http://{args.host}:{args.port}/health/
  2. Purchase Terminal  : http://{args.host}:{args.port}/
  3. Supplier Master    : http://{args.host}:{args.port}/parties/
  4. Flower Catalog     : http://{args.host}:{args.port}/flowers/
  5. Koyambedu Bill/PDF : http://{args.host}:{args.port}/invoice/
  6. Super Admin Console: http://{args.host}:{args.port}/super-admin/
  7. Register Shop      : http://{args.host}:{args.port}/register/
====================================================================
  Press CTRL+C to halt server cleanly.
"""
    print(banner)

    if args.prod:
        is_windows = platform.system() == "Windows"
        if is_windows:
            try:
                from waitress import serve
                from config.wsgi import application
                print(f"[Waitress] Serving production WSGI on http://{args.host}:{args.port}/ ...")
                serve(application, host=args.host, port=int(args.port), threads=8)
                return
            except ImportError:
                print("[Warn] Waitress not installed, falling back to Django runserver.")
        else:
            try:
                import subprocess
                cmd = ["gunicorn", "--config", "gunicorn.conf.py", f"--bind={args.host}:{args.port}", "config.wsgi:application"]
                subprocess.run(cmd)
                return
            except Exception as e:
                print(f"[Warn] Gunicorn launch error: {e}, falling back to Django runserver.")

    from django.core.management import execute_from_command_line
    sys.argv = ['manage.py', 'runserver', f"{args.host}:{args.port}"]
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
