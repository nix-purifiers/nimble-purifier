import ctypes
import json
from pathlib import Path
import resource
import sys

from cffi import FFI

view, expected, mode = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
catalog = json.loads((view / "catalog.json").read_text())
sys.path.insert(0, str(view))
import purifier_native

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
class DlInfo(ctypes.Structure):
    _fields_ = [("path", ctypes.c_char_p), ("base", ctypes.c_void_p),
                ("symbol", ctypes.c_char_p), ("address", ctypes.c_void_p)]

dladdr = ctypes.CDLL(None).dladdr
dladdr.argtypes = [ctypes.c_void_p, ctypes.POINTER(DlInfo)]
dladdr.restype = ctypes.c_int
rows = []
loaded = []  # Keep every runtime and its FFI object alive until process exit.
for name, path in catalog["libraries"].items():
    init = catalog["targets"][name]["runtime"]["init"]
    if mode in ["ctypes", "no-init"]:
        library = purifier_native.load(name)
        loaded.append(library)
        bootstrap = getattr(library, init)
        bootstrap.argtypes = []; bootstrap.restype = None
        if mode != "no-init": bootstrap()
        answer = library.nimAnswer; answer.argtypes = [ctypes.c_int]; answer.restype = ctypes.c_int
        values = [answer(0), answer(1)]
        address = ctypes.cast(answer, ctypes.c_void_p).value
    else:
        ffi = FFI(); ffi.cdef("void " + init + "(void); int nimAnswer(int);")
        library = ffi.dlopen(path)
        loaded.append((ffi, library))
        getattr(library, init)()
        values = [library.nimAnswer(0), library.nimAnswer(1)]
        address = int(ffi.cast("uintptr_t", library.nimAnswer))
    assert values == [expected, expected + 2], (name, values)
    info = DlInfo(); assert dladdr(address, ctypes.byref(info))
    assert Path(info.path.decode()).resolve() == Path(path).resolve()
    rows.append({"name": name, "values": values, "origin": str(Path(info.path.decode()).resolve()), "init": init})
print(json.dumps(rows))
