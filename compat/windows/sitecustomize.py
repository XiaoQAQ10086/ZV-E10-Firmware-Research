"""Windows compatibility shim for the zv-e10-toolkit host tools.

Injected through PYTHONPATH / sys.path only; the pinned toolkit checkout is
never modified. The host tools assume they run as root on macOS/Linux, where
they chown their private snapshots back to the invoking user. Windows has
neither a uid nor a chown, so this shim reports the single owning user and turns
ownership changes into no-ops. Nothing here touches the camera protocol
(pyusb / PMCA-RE).

``apply()`` is idempotent so a frozen build can call it explicitly even if the
module was imported earlier by the interpreter.

Adapted from the working ZV-E10 5GHz unlock procedure. Keep this file small and
auditable.
"""

import os
import sys
import types


def apply() -> None:
    if sys.platform != "win32":
        return

    if not hasattr(os, "geteuid"):
        os.geteuid = lambda: 0
    if not hasattr(os, "getuid"):
        os.getuid = lambda: 0
    if not hasattr(os, "getegid"):
        os.getegid = lambda: 0
    if not hasattr(os, "getgid"):
        os.getgid = lambda: 0
    if not hasattr(os, "chown"):
        os.chown = lambda *args, **kwargs: None

    if "pwd" not in sys.modules:
        pwd = types.ModuleType("pwd")

        def _unknown(uid):
            raise KeyError(uid)

        pwd.getpwuid = _unknown
        pwd.getpwnam = _unknown
        pwd.struct_passwd = tuple
        sys.modules["pwd"] = pwd

    try:
        import usb.backend.libusb1 as _libusb1
        import libusb_package

        _backend = _libusb1.get_backend(
            find_library=lambda name: libusb_package.get_library_path()
        )
        if _backend is not None:
            import usb.core

            if getattr(usb.core.find, "_zve10_backend_patched", False):
                return
            _original_find = usb.core.find

            def _find(*args, **kwargs):
                kwargs.setdefault("backend", _backend)
                return _original_find(*args, **kwargs)

            _find._zve10_backend_patched = True
            usb.core.find = _find
    except Exception:
        # Doctor reports the actual import/backend failure.
        pass


apply()
