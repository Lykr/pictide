"""Entry frozen by the portable builder."""
from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    import sys
    # The Windows EXE itself is the desktop entry. CLI and smoke retain stdout.
    if sys.platform == 'win32' and not any(option in sys.argv for option in ('--cli', '--no-browser', '--desktop', '--desktop-worker')):
        sys.argv.append('--desktop')
    from backend.host import main
    main()
