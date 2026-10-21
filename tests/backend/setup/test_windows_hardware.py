"""Dedicated-memory and adapter-selection boundaries for local model gates."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.setup.windows_hardware import _AdapterDesc, _adapter_record, _detect_ram, detect_hardware, select_gpu


class WindowsHardwareTests(unittest.TestCase):
    def test_adapter_memory_keeps_64_bits_and_excludes_shared_memory(self):
        desc = _AdapterDesc()
        desc.Description = 'NVIDIA GeForce RTX 4070 Ti'
        desc.VendorId = 0x10DE
        desc.DedicatedVideoMemory = 12 * 1024 ** 3
        desc.DedicatedSystemMemory = 2 * 1024 ** 3
        desc.SharedSystemMemory = 16 * 1024 ** 3
        self.assertEqual(_adapter_record(desc), {
            'profile': 'nvidia', 'name': 'NVIDIA GeForce RTX 4070 Ti',
            'vram_bytes': 12 * 1024 ** 3})
        desc.VendorId = 0x1414
        self.assertIsNone(_adapter_record(desc))
        desc.VendorId = 0x10DE
        desc.Description = 'Software Adapter'
        self.assertIsNone(_adapter_record(desc))

    def test_single_matching_gpu_and_vendor_priority(self):
        def card(profile, memory):
            return {'profile': profile, 'name': profile, 'vram_bytes': memory}

        hardware = {'gpus': [card('intel', 1), card('amd', 24 * 1024 ** 3),
                             card('nvidia', None), card('nvidia', 6 * 1024 ** 3),
                             card('nvidia', 8 * 1024 ** 3)]}
        self.assertIsNone(select_gpu(hardware)['vram_bytes'])
        self.assertIsNone(select_gpu(hardware, 'nvidia-cu126')['vram_bytes'])
        known = dict(hardware, gpus=[card('nvidia', 6 * 1024 ** 3), card('nvidia', 12 * 1024 ** 3)])
        self.assertEqual(select_gpu(known)['vram_bytes'], 6 * 1024 ** 3)
        self.assertEqual(select_gpu(hardware, 'amd')['vram_bytes'], 24 * 1024 ** 3)
        self.assertIsNone(select_gpu(hardware, 'cpu'))
        self.assertIsNone(select_gpu({'gpus': []}, 'nvidia'))

    def test_probe_failures_remain_independent_and_unknown(self):
        with patch('backend.setup.windows_hardware.sys.platform', 'win32'), \
                patch('backend.setup.windows_hardware._detect_gpus', side_effect=OSError), \
                patch('backend.setup.windows_hardware._detect_ram', return_value=32 * 1024 ** 3):
            self.assertEqual(detect_hardware(), {'gpus': [], 'ram_bytes': 32 * 1024 ** 3})
        with patch('backend.setup.windows_hardware.sys.platform', 'win32'), \
                patch('backend.setup.windows_hardware._detect_gpus', return_value=[]), \
                patch('backend.setup.windows_hardware._detect_ram', side_effect=OSError):
            self.assertEqual(detect_hardware(), {'gpus': [], 'ram_bytes': None})

        def installed(pointer):
            pointer._obj.value = 16 * 1024 ** 2  # Native API returns KiB.
            return 1

        def usable(pointer):
            pointer._obj.ullTotalPhys = 15 * 1024 ** 3
            return 1

        kernel = SimpleNamespace(GetPhysicallyInstalledSystemMemory=Mock(side_effect=installed),
                                 GlobalMemoryStatusEx=Mock(side_effect=usable))
        with patch('backend.setup.windows_hardware.ctypes.WinDLL', return_value=kernel, create=True):
            self.assertEqual(_detect_ram(), 16 * 1024 ** 3)
            kernel.GlobalMemoryStatusEx.assert_not_called()
            kernel.GetPhysicallyInstalledSystemMemory.side_effect = None
            kernel.GetPhysicallyInstalledSystemMemory.return_value = 0
            self.assertEqual(_detect_ram(), 15 * 1024 ** 3)


if __name__ == '__main__':
    unittest.main()
