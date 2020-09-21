import sys
from dataclasses import dataclass
from typing import Optional, List, Tuple

import OpenGL.GL as gl
import dolphin_memory_engine
import ghidra_bridge
import imgui
import pygame
from imgui.integrations.pygame import PygameRenderer

from retro_memory_viewer.memory_backend import MemoryBackend, NullBackend, DolphinBackend, BytesBackend

global_symbols = [
    {"name": "g_GameState", "type": "CGameState *", "address": 0x80418eb8},
    {"name": "g_CStateManager", "type": "CStateManager", "address": 0x803db6e0},
    {"name": "g_CSamusHud", "type": "CSamusHud *", "address": 0x803b1f30},
]
bridge: ghidra_bridge.GhidraBridge

windows = []
data_types = {}

memory_backend: MemoryBackend = NullBackend()


@dataclass(frozen=True)
class DataTypeComponent:
    offset: int
    length: int
    type: str
    name: Optional[str]
    comment: Optional[str]

    @classmethod
    def from_json(cls, data) -> "DataTypeComponent":
        return DataTypeComponent(
            data["offset"],
            data["length"],
            data["type"],
            data["name"],
            data["comment"],
        )


@dataclass(frozen=True)
class DataType:
    name: str
    length: int
    components: List[DataTypeComponent]

    @classmethod
    def from_json(cls, data) -> "DataType":
        return DataType(
            name=data["name"],
            length=data["length"],
            components=[
                DataTypeComponent.from_json(component)
                for component in data["components"]
            ]
        )


def get_array_size(data_type: str) -> Tuple[str, int]:
    if data_type[-1] != "]":
        return data_type, 1

    starting_bracket = data_type.rfind("[")
    size = int(data_type[starting_bracket + 1:-1])
    return data_type[:starting_bracket], size


def is_array(data_type: str) -> bool:
    return False


class DataTypeWindow:
    def __init__(self, address: int, data_type, title: str):
        self.title = title
        self.address = address

        result = bridge.remote_eval("""
        {
            "data_length": data_type.getLength(),
            "components": [
                serialize_component(component)
                for component in data_type.getComponents()
                if component.getDataType().getName() != "undefined"
            ],
        }
        """, data_type=data_type)
        self.data_length = result["data_length"]
        self.components = result["components"]

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
                data_in_memory = memory[base_address:base_address + component["element_size"]]
                if component["is_pointer"] or component["is_struct"]:
                    if component["is_pointer"]:
                        text_message = f"Open: 0x{data_in_memory.hex()}"
                    else:
                        text_message = f"Open##{component['offset']}"
                    if imgui.button(text_message):
                        open_type_window(self.address + base_address, component["element_type"], component["name"])
                else:
                    imgui.text(data_in_memory.hex())
                imgui.next_column()

        imgui.columns(1)


def open_type_window(address: int, data_type, name: str):
    pointers = []

    base_address = address
    while isinstance(data_type, ghidra.program.database.data.PointerDB):
        pointers.append(0)
        data_type = data_type.getDataType()

    real_address = dolphin_memory_engine.follow_pointers(base_address, pointers)

    windows.append(DataTypeWindow(real_address, data_type, f"{name} - {data_type.getName()} @ {hex(real_address)}"))


def save_memory_to_file():
    mem1 = memory_backend.read_bytes(BytesBackend.MEM1_START, BytesBackend.MEM1_SIZE)
    with open("mem1.bin", "wb") as mem_file:
        mem_file.write(mem1)


def loop():
    pygame.init()
    size = 800, 600

    global memory_backend

    pygame.display.set_mode(size, pygame.DOUBLEBUF | pygame.OPENGL | pygame.RESIZABLE)

    imgui.create_context()
    impl = PygameRenderer()

    io = imgui.get_io()
    io.display_size = size
    bridge.remote_exec("""
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
    return result
    
def get_symbol_type(symbol):
    data = getDataAt(symbol.getAddress())
    if data is not None:
        return data.getDataType()
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
                if imgui.menu_item("Hook to Dolphin", enabled=not isinstance(memory_backend, DolphinBackend))[0]:
                    dolphin_memory_engine.hook()
                    if dolphin_memory_engine.is_hooked():
                        memory_backend = DolphinBackend(dolphin_memory_engine)

                if imgui.menu_item("Read from File", enabled=not isinstance(memory_backend, BytesBackend))[0]:
                    try:
                        with open("mem1.bin", "rb") as mem_file:
                            memory_backend = BytesBackend(mem_file.read())
                    except FileNotFoundError:
                        pass

                if imgui.menu_item("Save to File", enabled=memory_backend.is_connected)[0]:
                    save_memory_to_file()

                imgui.end_menu()

            imgui.end_main_menu_bar()

        # imgui.show_test_window()

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

        # note: cannot use screen.fill((1, 1, 1)) because pygame's screen
        #       does not support fill() on OpenGL sufraces
        gl.glClearColor(0, 0, 0, 1)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        imgui.render()
        impl.render(imgui.get_draw_data())

        pygame.display.flip()


def main_loop():
    global bridge
    with ghidra_bridge.GhidraBridge(namespace=globals()) as gb:
        bridge = gb
        loop()
