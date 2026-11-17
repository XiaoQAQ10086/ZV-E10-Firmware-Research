try:
    from .cli import main
except ImportError:  # PyInstaller runs this file as the top-level __main__
    from zve10_installer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
