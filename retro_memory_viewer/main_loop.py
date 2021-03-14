import json
import struct
import sys
from pathlib import Path
from typing import Dict

import OpenGL.GL as gl
import dolphin_memory_engine
import ghidra_bridge
import imgui
import pygame
from imgui.integrations.pygame import PygameRenderer

from retro_memory_viewer.memory_backend import MemoryBackend, NullBackend, DolphinBackend, BytesBackend

windows = []

memory_backend: MemoryBackend = NullBackend()
all_types: Dict[str, dict] = {}


class DataTypeWindow:
    def __init__(self, address: int, data_type: dict, title: str):
        self.title = title
        self.address = address
        self.data_length = data_type["data_length"]
        self.components = data_type["components"]

    def render(self):
        memory = memory_backend.read_bytes(self.address, self.data_length)
        imgui.columns(4)
        for component in self.components:
            imgui.text(hex(component["offset"]))
            imgui.next_column()
            imgui.text(component["type_name"])
            imgui.next_column()
            imgui.text(component["name"])
            imgui.next_column()

            for i in range(component["array_size"]):
                if i > 0:
                    imgui.next_column()
                    imgui.next_column()
                    imgui.next_column()

                base_address = component["offset"] + i * component["element_size"]
                if component["is_pointer"] or component["is_struct"]:
                    if component["is_pointer"]:
                        data_in_memory = memory[base_address:base_address + component["element_size"]]
                        text_message = f"Open: 0x{data_in_memory.hex()}"
                    else:
                        text_message = f"Open##{component['offset']}"
                    if imgui.button(text_message):
                        open_type_window(self.address + base_address, component["element_type"], component["name"])
                else:
                    if component["type_name"] == "float":
                        value = str(struct.unpack_from(">f", memory, base_address)[0])
                    else:
                        data_in_memory = memory[base_address:base_address + component["element_size"]]
                        value = data_in_memory.hex()
                    imgui.text(value)
                imgui.next_column()

        imgui.columns(1)


def open_type_window(address: int, type_name: str, name: str):
    pointers = []
    data_type = all_types[type_name]

    base_address = address
    while "pointer" in data_type:
        pointers.append(0)
        data_type = all_types[data_type["pointer"]]

    real_address = memory_backend.follow_pointers(base_address, pointers)

    windows.append(DataTypeWindow(real_address, data_type, f"{name} - {data_type['name']} @ {hex(real_address)}"))


def save_memory_to_file():
    mem1 = memory_backend.read_bytes(BytesBackend.MEM1_START, BytesBackend.MEM1_SIZE)
    with open("mem1.bin", "wb") as mem_file:
        mem_file.write(mem1)


def load_symbols_from_ghidra():
    with ghidra_bridge.GhidraBridge(namespace=globals()) as bridge:
        bridge.remote_exec("""
all_types = {}

def serialize_type(data_type):
    name = data_type.getName()
    if name in all_types:
        return name
    all_types[name] = True

    if isinstance(data_type, ghidra.program.database.data.PointerDB):
        all_types[name] = {
            "name": name,
            "pointer": serialize_type(data_type.getDataType())
        }
    elif isinstance(data_type, ghidra.program.database.data.StructureDB):
        all_types[name] = {
            "name": name,
            "data_length": data_type.getLength(),
            "components": [
                serialize_component(component)
                for component in data_type.getComponents()
                if component.getDataType().getName() != "undefined"
            ],
        }
    else:
        print(type(data_type))

    return name


def serialize_component(component):
    component_name = component.getFieldName()
    if component_name is None:
        component_name = "<unknown>"

    result = {
        "offset": component.getOffset(),
        "type_name": component.getDataType().getName(),
        "length": component.getLength(),
        "name": component_name,
        "comment": component.getComment(),
    }
    if isinstance(component.getDataType(), ghidra.program.database.data.ArrayDB):
        result["array_size"] = component.getDataType().getNumElements()
        result["element_type"] = component.getDataType().getDataType()
    else: 
        result["array_size"] = 1
        result["element_type"] = component.getDataType()

    result["element_size"] = result["element_type"].getLength()
    result["is_pointer"] = isinstance(result["element_type"], ghidra.program.database.data.PointerDB)
    result["is_struct"] = isinstance(result["element_type"], ghidra.program.database.data.StructureDB)
    result["element_type"] = serialize_type(result["element_type"])
    return result

def get_symbol_type(symbol):
    data = getDataAt(symbol.getAddress())
    if data is not None:
        return serialize_type(data.getDataType())
    return None
    """)
        main_symbols = bridge.remote_eval("""[
            {
                "name": symbol.getName(True),
                "address": symbol.getAddress().getOffset(),
                "type": get_symbol_type(symbol),
            }
            for symbol in currentProgram.getSymbolTable().getDefinedSymbols()
            if symbol.getName().startswith("g_")
        ]
        """)
        ghidra_types = dict(sorted(bridge.remote_eval("all_types").items(), key=lambda k: k[0]))

    return main_symbols, ghidra_types


def save_symbols_to_file(main_symbols, all_data_types):
    with open("symbols.json", "w") as symbols_file:
        json.dump({
            "main_symbols": main_symbols,
            "all_types": all_data_types,
        }, symbols_file)


def load_symbols_from_file():
    with open("symbols.json", "r") as symbols_file:
        data = json.load(symbols_file)
    return data["main_symbols"], data["all_types"]


def loop():
    pygame.init()
    size = 800, 600

    global memory_backend

    pygame.display.set_mode(size, pygame.DOUBLEBUF | pygame.OPENGL | pygame.RESIZABLE)

    imgui.create_context()
    impl = PygameRenderer()

    io = imgui.get_io()
    io.display_size = size

    global all_types
    main_symbols = []

    if Path("symbols.json").exists():
        try:
            main_symbols, all_types = load_symbols_from_file()
        except json.JSONDecodeError:
            pass

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit()

            impl.process_event(event)

        if not memory_backend.is_connected and not isinstance(memory_backend, NullBackend):
            memory_backend = NullBackend()

        imgui.new_frame()

        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):

                clicked_quit, selected_quit = imgui.menu_item(
                    "Quit", 'Cmd+Q', False, True
                )

                if clicked_quit:
                    raise SystemExit(0)

                imgui.end_menu()

            if imgui.begin_menu(f"Memory: {memory_backend.name}", True):
                if imgui.menu_item("Disconnect")[0]:
                    memory_backend = NullBackend()

                if imgui.menu_item("Save to File", enabled=memory_backend.is_connected)[0]:
                    save_memory_to_file()

                imgui.end_menu()

            if imgui.begin_menu(f"Symbols", True):
                if imgui.menu_item("Load from File")[0]:
                    main_symbols, all_types = load_symbols_from_file()

                if imgui.menu_item("Load from Ghidra")[0]:
                    main_symbols, all_types = load_symbols_from_ghidra()

                if imgui.menu_item("Save to File")[0]:
                    save_symbols_to_file(main_symbols, all_types)

                imgui.end_menu()

            imgui.end_main_menu_bar()

        # imgui.show_test_window()

        if memory_backend.is_connected:
            imgui.begin("Globals")
            for symbol in main_symbols:
                if symbol["type"] is None:
                    imgui.text(f"{symbol['name']} - No type")
                else:
                    if imgui.button(f"{symbol['name']}##{symbol['address']}"):
                        open_type_window(symbol["address"], symbol["type"], symbol['name'])
            imgui.end()

            windows_to_delete = []
            for window in windows:
                imgui.set_next_window_size(600, 400, imgui.ONCE)
                expanded, opened = imgui.begin(window.title, True)
                if expanded:
                    window.render()
                if not opened:
                    windows_to_delete.append(window)
                imgui.end()

            for window in windows_to_delete:
                windows.remove(window)
        else:
            imgui.begin("Connect to...")
            if imgui.button("Hook to Dolphin"):
                dolphin_memory_engine.hook()
                if dolphin_memory_engine.is_hooked():
                    memory_backend = DolphinBackend(dolphin_memory_engine)

            if imgui.button("Read from File"):
                try:
                    with open("mem1.bin", "rb") as mem_file:
                        memory_backend = BytesBackend(mem_file.read())
                except FileNotFoundError:
                    pass
            imgui.end()

        # note: cannot use screen.fill((1, 1, 1)) because pygame's screen
        #       does not support fill() on OpenGL sufraces
        gl.glClearColor(0, 0, 0, 1)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        imgui.render()
        impl.render(imgui.get_draw_data())

        pygame.display.flip()


def main_loop():
    return loop()
