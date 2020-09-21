import struct
from typing import List

import dolphin_memory_engine


class MemoryBackend:
    @property
    def name(self) -> str:
        raise NotImplementedError()

    @property
    def is_connected(self) -> bool:
        raise NotImplementedError()

    def read_bytes(self, address: int, length: int) -> bytes:
        raise NotImplementedError()

    def follow_pointers(self, console_address: int, pointer_offsets: List[int]) -> int:
        raise NotImplementedError()


class NullBackend(MemoryBackend):
    @property
    def name(self) -> str:
        return "Nothing"

    @property
    def is_connected(self) -> bool:
        return False

    def read_bytes(self, address: int, length: int) -> bytes:
        raise RuntimeError("Unavailable")

    def follow_pointers(self, console_address: int, pointer_offsets: List[int]) -> int:
        raise RuntimeError("Unavailable")


class DolphinBackend(MemoryBackend):
    def __init__(self, backend: dolphin_memory_engine):
        self.dolphin = backend

    @property
    def name(self) -> str:
        return "Dolphin"

    @property
    def is_connected(self) -> bool:
        return self.dolphin.is_hooked()

    def read_bytes(self, address: int, length: int) -> bytes:
        return self.dolphin.read_bytes(address, length)

    def follow_pointers(self, console_address: int, pointer_offsets: List[int]) -> int:
        return self.dolphin.follow_pointers(console_address, pointer_offsets)


class BytesBackend(MemoryBackend):
    MEM1_START = 0x80000000
    MEM1_SIZE = 0x1800000

    def __init__(self, data: bytes):
        self.data = data

    @property
    def name(self) -> str:
        return "File"

    @property
    def is_connected(self) -> bool:
        return True

    def _address_to_offset(self, address: int) -> int:
        return address - self.MEM1_START

    def _check_valid_address(self, address: int):
        if not (self.MEM1_START <= address < self.MEM1_START + self.MEM1_SIZE):
            raise RuntimeError(f"Address {address} is not valid")

    def read_bytes(self, address: int, length: int) -> bytes:
        self._check_valid_address(address)
        converted = self._address_to_offset(address)
        return self.data[converted:converted + length]

    def follow_pointers(self, console_address: int, pointer_offsets: List[int]) -> int:
        real_console_address = console_address

        for offset in pointer_offsets:
            memory_buffer = self.read_bytes(real_console_address, 4)
            real_console_address = struct.unpack(">L", memory_buffer)[0]
            self._check_valid_address(real_console_address)
            real_console_address += offset

        return real_console_address
