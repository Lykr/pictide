"""Entry frozen by the portable builder."""
from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    from backend.host import main
    main()
