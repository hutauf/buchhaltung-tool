"""Run the official OTS CLI; resolve Git for Windows' OpenSSL if needed."""
import ctypes.util
import os
from pathlib import Path


def main():
    if os.name == "nt" and not ctypes.util.find_library("ssl"):
        dll = Path(os.environ.get("OTS_LIBCRYPTO_DLL", "C:/Program Files/Git/mingw64/bin/libcrypto-3-x64.dll"))
        if not dll.is_file():
            raise RuntimeError("OpenSSL fehlt. OTS_LIBCRYPTO_DLL auf eine vertrauenswürdige OpenSSL-DLL setzen.")
        original = ctypes.util.find_library
        ctypes.util.find_library = lambda name: str(dll) if name in ("ssl.35", "ssl", "libeay32") else original(name)
    from otsclient.ots import main as ots_main
    return ots_main()


if __name__ == "__main__":
    main()
