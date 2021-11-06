import json
import struct
import tkinter
import tkinter.filedialog
import typing
from contextlib import ExitStack
from pathlib import Path
from typing import Dict, Optional

import OpenGL.GL as gl
import glfw
import imgui
from imgui.integrations.glfw import GlfwRenderer
from mercury_engine_data_structures import hashed_names
from mercury_engine_data_structures.pkg_editor import PkgEditor

all_types: Dict[str, dict] = {}

preferences: Dict[str, typing.Any] = {}
preferences_file_path = Path(__file__).parent.joinpath("preferences.json")


def save_preferences():
    with preferences_file_path.open("w") as f:
        json.dump(preferences, f, indent=4)


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


def prompt_file(directory: bool):
    """Create a Tk file dialog and cleanup when finished"""
    top = tkinter.Tk()
    top.withdraw()  # hide window
    if directory:
        file_name = tkinter.filedialog.askdirectory(parent=top)
    else:
        file_name = tkinter.filedialog.askopenfilename(parent=top)
    top.destroy()
    return file_name


def impl_glfw_init():
    width, height = 1280, 720
    window_name = "minimal ImGui/GLFW3 example"

    if not glfw.init():
        print("Could not initialize OpenGL context")
        exit(1)

    # OS X supports only forward-compatible core profiles from 3.2
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)

    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, gl.GL_TRUE)
    glfw.window_hint(glfw.SCALE_TO_MONITOR, glfw.TRUE)

    # Create a windowed mode window and its OpenGL context
    window = glfw.create_window(
        int(width), int(height), window_name, None, None
    )
    glfw.make_context_current(window)

    if not window:
        glfw.terminate()
        print("Could not initialize Window")
        exit(1)

    return window


def loop():
    imgui.create_context()
    window = impl_glfw_init()
    impl = GlfwRenderer(window)

    global preferences
    if preferences_file_path.exists():
        preferences = json.loads(preferences_file_path.read_text())

    pkg_editor: Optional[PkgEditor] = None
    possible_brfld = []

    with ExitStack() as stack:
        def load_romfs(path: Path):
            nonlocal pkg_editor, possible_brfld
            stack.close()
            pkg_editor = stack.enter_context(PkgEditor.open_pkgs_at(path))
            possible_brfld = [
                name
                for asset_id in pkg_editor.all_asset_ids()
                if (name := hashed_names.name_for_asset_id(asset_id)) is not None
                   and name.endswith("brfld")
            ]
            preferences["last_romfs"] = str(path)
            save_preferences()

        if preferences.get("last_romfs") is not None:
            try:
                load_romfs(Path(preferences["last_romfs"]))
            except Exception as e:
                print(f"Unable to re-open last romfs: {e}")
                preferences["last_romfs"] = None
                save_preferences()

        while not glfw.window_should_close(window):
            glfw.poll_events()
            impl.process_inputs()
            imgui.get_io().font_global_scale = glfw.get_window_content_scale(window)[0]

            imgui.new_frame()

            if imgui.begin_main_menu_bar():
                if imgui.begin_menu("File", True):

                    if imgui.menu_item("Open Dread romfs root")[0]:
                        f = prompt_file(directory=True)
                        if f:
                            load_romfs(Path(f))

                    clicked_quit, selected_quit = imgui.menu_item(
                        "Quit", 'Cmd+Q', False, True
                    )

                    if clicked_quit:
                        raise SystemExit(0)

                    imgui.end_menu()

                imgui.end_main_menu_bar()

            if possible_brfld:
                imgui.begin("Select file to open", True)
                for file in sorted(possible_brfld):
                    imgui.bullet()
                    if imgui.small_button(file):
                        pass
                imgui.end()

            imgui.show_test_window()

            gl.glClearColor(0, 0, 0, 1)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT)

            imgui.render()
            impl.render(imgui.get_draw_data())
            glfw.swap_buffers(window)

    impl.shutdown()
    glfw.terminate()


def main_loop():
    return loop()
