"""Read Windows adapter memory and physical RAM without external utilities."""
import ctypes
import sys
import uuid


_VENDORS = {0x10DE: 'nvidia', 0x1002: 'amd', 0x8086: 'intel'}


class _GUID(ctypes.Structure):
    _fields_ = [('Data1', ctypes.c_uint32), ('Data2', ctypes.c_uint16),
                ('Data3', ctypes.c_uint16), ('Data4', ctypes.c_ubyte * 8)]


class _LUID(ctypes.Structure):
    _fields_ = [('LowPart', ctypes.c_uint32), ('HighPart', ctypes.c_int32)]


class _AdapterDesc(ctypes.Structure):
    _fields_ = [('Description', ctypes.c_wchar * 128),
                ('VendorId', ctypes.c_uint32), ('DeviceId', ctypes.c_uint32),
                ('SubSysId', ctypes.c_uint32), ('Revision', ctypes.c_uint32),
                ('DedicatedVideoMemory', ctypes.c_size_t),
                ('DedicatedSystemMemory', ctypes.c_size_t),
                ('SharedSystemMemory', ctypes.c_size_t), ('AdapterLuid', _LUID)]


class _MemoryStatus(ctypes.Structure):
    _fields_ = [('dwLength', ctypes.c_uint32), ('dwMemoryLoad', ctypes.c_uint32),
                ('ullTotalPhys', ctypes.c_uint64), ('ullAvailPhys', ctypes.c_uint64),
                ('ullTotalPageFile', ctypes.c_uint64), ('ullAvailPageFile', ctypes.c_uint64),
                ('ullTotalVirtual', ctypes.c_uint64), ('ullAvailVirtual', ctypes.c_uint64),
                ('ullAvailExtendedVirtual', ctypes.c_uint64)]


def _method(pointer, index, result, *arguments):
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *arguments)(vtable[index])


def _release(pointer):
    if pointer:
        _method(pointer, 2, ctypes.c_uint32)(pointer)


def _adapter_record(desc):
    profile = _VENDORS.get(desc.VendorId)
    name = desc.Description.strip()
    if profile is None or not name or 'software' in name.lower():
        return None
    # SharedSystemMemory and DedicatedSystemMemory are deliberately excluded.
    return {'profile': profile, 'name': name,
            'vram_bytes': int(desc.DedicatedVideoMemory)}


def _detect_gpus():
    dxgi = ctypes.WinDLL('dxgi', use_last_error=True)
    create = dxgi.CreateDXGIFactory
    create.argtypes = [ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    create.restype = ctypes.c_int32
    iid = _GUID.from_buffer_copy(uuid.UUID('7b7166ec-21c7-44ae-b21a-c9ae321ae369').bytes_le)
    factory = ctypes.c_void_p()
    if create(ctypes.byref(iid), ctypes.byref(factory)) < 0:
        raise OSError('DXGI factory could not be created')
    adapters = []
    try:
        enum = _method(factory, 7, ctypes.c_int32, ctypes.c_uint32,
                       ctypes.POINTER(ctypes.c_void_p))
        index = 0
        while True:
            adapter = ctypes.c_void_p()
            status = enum(factory, index, ctypes.byref(adapter))
            if status & 0xFFFFFFFF == 0x887A0002:  # DXGI_ERROR_NOT_FOUND
                break
            if status < 0:
                raise OSError('DXGI adapters could not be enumerated')
            try:
                desc = _AdapterDesc()
                get_desc = _method(adapter, 8, ctypes.c_int32, ctypes.POINTER(_AdapterDesc))
                if get_desc(adapter, ctypes.byref(desc)) >= 0:
                    record = _adapter_record(desc)
                    if record is not None:
                        adapters.append(record)
            finally:
                _release(adapter)
            index += 1
    finally:
        _release(factory)
    return adapters


def _detect_ram():
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    # Installed capacity avoids subtracting firmware-reserved RAM from a model's
    # hardware tier. Older/unsupported firmware can fall back to usable RAM.
    installed = ctypes.c_uint64()
    try:
        read_installed = kernel32.GetPhysicallyInstalledSystemMemory
        read_installed.argtypes = [ctypes.POINTER(ctypes.c_uint64)]
        read_installed.restype = ctypes.c_int32
        if read_installed(ctypes.byref(installed)) and installed.value:
            return int(installed.value) * 1024
    except (OSError, AttributeError):
        pass
    read = kernel32.GlobalMemoryStatusEx
    read.argtypes = [ctypes.POINTER(_MemoryStatus)]
    read.restype = ctypes.c_int32
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not read(ctypes.byref(status)):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(status.ullTotalPhys) or None


def detect_hardware():
    """Return dedicated VRAM and installed RAM (usable physical RAM fallback)."""
    hardware = {'gpus': [], 'ram_bytes': None}
    if sys.platform != 'win32':
        return hardware
    errors = (OSError, ValueError, AttributeError, ctypes.ArgumentError)
    try:
        hardware['gpus'] = _detect_gpus()
    except errors:
        pass
    try:
        hardware['ram_bytes'] = _detect_ram()
    except errors:
        pass
    return hardware


def select_gpu(hardware, profile_id=None):
    """Use the smallest matching card while ComfyUI's execution card is unbound."""
    if profile_id == 'cpu':
        return None
    profile = 'nvidia' if profile_id == 'nvidia-cu126' else profile_id
    cards = hardware.get('gpus', [])
    profiles = [profile] if profile else ['nvidia', 'amd', 'intel']
    for vendor in profiles:
        matches = [card for card in cards if card.get('profile') == vendor]
        if matches:
            return min(matches, key=lambda card: card.get('vram_bytes')
                       if card.get('vram_bytes') is not None else -1)
    return None
