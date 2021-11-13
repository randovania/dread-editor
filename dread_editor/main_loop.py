import logging
import tkinter
import tkinter.filedialog
import typing
from pathlib import Path
from typing import Optional

import OpenGL.GL as gl
import glfw
import imgui
from imgui.integrations.glfw import GlfwRenderer
from mercury_engine_data_structures.pkg_editor import PkgEditor
from mercury_engine_data_structures.type_lib import BaseType

from dread_editor import type_render, imgui_util
from dread_editor.level_data import LevelData
from dread_editor.preferences import global_preferences, load_preferences, save_preferences
from dread_editor.type_render import SpecificTypeRender, TypeTreeRender

all_bmsad_actordefs = []


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
    window_name = "Dread Level Editor"

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


current_level_data: Optional[LevelData] = None


class AssetLinkRender(SpecificTypeRender):
    def uses_one_column(self, type_data: BaseType):
        return True

    def create_default(self, type_data: BaseType):
        return all_bmsad_actordefs[0]

    def render_value(self, value: typing.Any, type_data: BaseType, path: str):
        if path.endswith(".oActorDefLink"):
            result = imgui_util.combo_str(f"##{path}", value, all_bmsad_actordefs)
            imgui_util.set_hovered_tooltip(value)
            return result
        else:
            return type_render.render_string(value, path)


def add_custom_type_renders(tree_render: TypeTreeRender):
    tree_render.specific_renders["base::core::CAssetLink"] = AssetLinkRender()


def loop():
    imgui.create_context()
    window = impl_glfw_init()
    impl = GlfwRenderer(window)

    global current_level_data

    load_preferences()

    pkg_editor: Optional[PkgEditor] = None
    current_error_message = None
    possible_brfld = []

    def load_romfs(path: Path):
        nonlocal pkg_editor, possible_brfld
        pkg_editor = PkgEditor(path)
        possible_brfld = [
            asset_name
            for asset_name in pkg_editor.all_asset_names()
            if asset_name.endswith("brfld")
        ]
        possible_brfld.sort()
        all_bmsad_actordefs.clear()
        all_bmsad_actordefs.extend([
            f"actordef:{asset_name}"
            for asset_name in pkg_editor.all_asset_names()
            if asset_name.endswith("bmsad")
        ])

        all_bmsad_actordefs.sort()

        global_preferences["last_romfs"] = str(path)
        save_preferences()

    if global_preferences.get("last_romfs") is not None:
        try:
            load_romfs(Path(global_preferences["last_romfs"]))
        except Exception as e:
            logging.exception(f"Unable to re-open last romfs: {e}")
            global_preferences["last_romfs"] = None
            save_preferences()

    while not glfw.window_should_close(window):
        glfw.poll_events()
        impl.process_inputs()
        current_scale = glfw.get_window_content_scale(window)[0]
        imgui.get_io().font_global_scale = current_scale

        imgui.new_frame()

        if current_error_message is not None:
            imgui.open_popup("Error")
            if imgui.begin_popup_modal("Error")[0]:
                imgui.text(current_error_message)
                if imgui.button("Ok"):
                    current_error_message = None
                imgui.end_popup()

        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):
                if imgui.menu_item("Select extracted Metroid Dread root")[0]:
                    f = prompt_file(directory=True)
                    if f:
                        load_romfs(Path(f))

                imgui.text_disabled(f'* Current root: {global_preferences.get("last_romfs")}')
                imgui.separator()

                if imgui.menu_item("Save changes")[0]:
                    if pkg_editor is None:
                        current_error_message = "Unable to save, no root selected."
                    else:
                        if current_level_data is not None:
                            current_level_data.apply_changes_to(pkg_editor)
                        pkg_editor.save_modified_pkgs()

                imgui.end_menu()

            if imgui.begin_menu("Select level file", len(possible_brfld) > 0):
                current_file_name = None
                if current_level_data is not None:
                    current_file_name = current_level_data.file_name

                for name in possible_brfld:
                    if imgui.menu_item(name, "", name == current_file_name)[0]:
                        current_level_data = LevelData.open_file(pkg_editor, name)
                        add_custom_type_renders(current_level_data.tree_render)

                imgui.end_menu()

            imgui.end_main_menu_bar()

        if current_level_data is not None:
            if not current_level_data.render_window(current_scale):
                current_level_data = None

        if current_level_data is not None:
            current_level_data.draw_visible_actors(current_scale)

        # imgui.show_test_window()

        gl.glClearColor(0, 0, 0, 1)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        imgui.render()
        impl.render(imgui.get_draw_data())
        glfw.swap_buffers(window)

    impl.shutdown()
    glfw.terminate()


def main_loop():
    return loop()
