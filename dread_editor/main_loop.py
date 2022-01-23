import logging
import tkinter
import tkinter.filedialog
import typing
from pathlib import Path
from typing import Optional

import OpenGL.GL as gl
import construct
import glfw
import imgui
from imgui.integrations.glfw import GlfwRenderer
from mercury_engine_data_structures import type_lib
from mercury_engine_data_structures.formats import Bmsad
from mercury_engine_data_structures.formats.bmsad import find_charclass_for_type
from mercury_engine_data_structures.file_tree_editor import FileTreeEditor
from mercury_engine_data_structures.type_lib import BaseType

from dread_editor import type_render, imgui_util
from dread_editor.file_browser import FileBrowser
from dread_editor.level_data import LevelData
from dread_editor.preferences import global_preferences, load_preferences, save_preferences
from dread_editor.type_render import SpecificTypeRender, TypeTreeRender

PathsByDirectory = dict[str, typing.Union[str, "PathsByDirectory"]]

all_bmsad: list[str] = []
nested_bmsad: PathsByDirectory = {}
all_bmsad_actordefs: list[str] = []
nested_all_files: PathsByDirectory = {}

open_bmsad: dict[str, Bmsad] = {}
glfw_window = None

bmsad_tree_render = TypeTreeRender()


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

            if imgui.begin_popup_context_item(f"{path}_context"):
                if imgui.menu_item("Copy text")[0]:
                    glfw.set_clipboard_string(glfw_window, value)
                imgui.end_popup()
            else:
                imgui_util.set_hovered_tooltip(value)

            return result
        else:
            return type_render.render_string(value, path)


def add_custom_type_renders(tree_render: TypeTreeRender):
    tree_render.specific_renders["base::core::CAssetLink"] = AssetLinkRender()


def clean_single_item_directory(directory: PathsByDirectory) -> PathsByDirectory:
    if isinstance(directory, str):
        return directory

    result = {}
    for key, value in directory.items():
        if isinstance(value, str):
            result[key] = value
        elif len(value) > 1:
            result[key] = clean_single_item_directory(value)
        else:
            # the way split_directories works, they're never empty
            assert len(value) > 0
            nested_key, nested_value = list(value.items())[0]
            result[f"{key}/{nested_key}"] = clean_single_item_directory(nested_value)

    return result


def split_directories(files: list[str]) -> PathsByDirectory:
    result = {}

    for item in files:
        parent = result
        for part in item.split("/"):
            assert len(part) > 0
            if part not in parent:
                if part.endswith(".bmsad"):
                    parent[part] = item
                else:
                    parent[part] = {}
            parent = parent[part]

    return clean_single_item_directory(result)


def draw_open_bmsad(current_scale: float):
    string_vector = type_lib.get_type("base::global::CRntVector<base::global::CStrId>")

    for path, bmsad in list(open_bmsad.items()):
        active = imgui.begin(path, True)[1]
        if not active:
            open_bmsad.pop(path)
            imgui.end()
            continue

        imgui.columns(2, "bmsad details")
        imgui.text("Name")
        imgui.next_column()
        imgui.text(bmsad.raw.name)
        imgui.next_column()

        imgui.text("Type")
        imgui.next_column()
        imgui.text(bmsad.raw.type)
        imgui.next_column()

        imgui.separator()
        prop = bmsad.raw.property

        imgui.text("Model Name")
        imgui.next_column()
        imgui.text(prop.model_name)
        imgui.next_column()

        node_open = imgui.tree_node("Sub Actors", imgui.TREE_NODE_DEFAULT_OPEN)
        imgui.next_column()
        imgui.next_column()
        if node_open:
            changed, new_field = bmsad_tree_render.render_value_of_type(prop.sub_actors, string_vector, "sub_actors")
            if changed:
                prop.sub_actors = new_field
            imgui.tree_pop()

        if imgui_util.tree_node_with_column("Components", imgui.TREE_NODE_DEFAULT_OPEN):
            if isinstance(prop.components, construct.Container):
                for component_key, component in prop.components.items():
                    if imgui_util.tree_node_with_column(component_key):
                        imgui.text("Type")
                        imgui.next_column()
                        imgui.text(component.type)
                        imgui.next_column()

                        # Fields
                        if component.fields is not None and imgui_util.tree_node_with_column(
                                f"Fields ##{component_key}_fields", imgui.TREE_NODE_DEFAULT_OPEN):
                            changed, new_field = bmsad_tree_render.render_value_of_type(
                                component.fields.fields,
                                type_lib.get_type(find_charclass_for_type(component.type)),
                                f"{component_key}"
                            )
                            if changed:
                                component.fields.fields = new_field
                            imgui.tree_pop()

                        # Extra Fields
                        if imgui_util.tree_node_with_column("Extra Fields", imgui.TREE_NODE_DEFAULT_OPEN):
                            imgui.text(str(component.extra_fields))
                            imgui.tree_pop()

                        # Functions
                        if imgui_util.tree_node_with_column("Functions", imgui.TREE_NODE_DEFAULT_OPEN):
                            for i, function in enumerate(component.functions):
                                node_open = imgui_util.tree_node_with_column(
                                    f"{function.name}##{component_key}_functions_{i}", imgui.TREE_NODE_DEFAULT_OPEN)
                                if node_open:
                                    for param_name, param in function.params.items():
                                        imgui.text(param_name)
                                        imgui.next_column()
                                        imgui.text(str(param.value))
                                        imgui.next_column()
                                    imgui.tree_pop()
                            imgui.tree_pop()

                        if component.dependencies is not None and imgui_util.tree_node_with_column(
                                "Dependencies", imgui.TREE_NODE_DEFAULT_OPEN):
                            imgui.next_column()
                            imgui.text(str(component.dependencies))
                            imgui.next_column()
                            imgui.tree_pop()

                        if imgui_util.tree_node_with_column("Raw"):
                            imgui.next_column()
                            imgui.text(str(component))
                            imgui.next_column()
                            imgui.tree_pop()

                        imgui.tree_pop()

            imgui.tree_pop()

        imgui.columns(1, "bmsad details")
        if imgui.tree_node("Raw"):
            imgui.text(str(bmsad.raw))
            imgui.tree_pop()
        imgui.end()


def loop():
    imgui.create_context()
    window = impl_glfw_init()
    impl = GlfwRenderer(window)

    global current_level_data, glfw_window

    glfw_window = window
    load_preferences()

    file_browser: Optional[FileBrowser] = None
    pkg_editor: Optional[FileTreeEditor] = None
    current_error_message = None
    pending_load_last_romfs = True
    possible_brfld = []

    def load_romfs(path: Path):
        nonlocal pkg_editor, possible_brfld, file_browser
        pkg_editor = FileTreeEditor(path)
        possible_brfld = [
            asset_name
            for asset_name in pkg_editor.all_asset_names()
            if asset_name.endswith("brfld")
        ]
        possible_brfld.sort()
        all_bmsad.clear()
        all_bmsad.extend(
            asset_name
            for asset_name in pkg_editor.all_asset_names()
            if asset_name.endswith("bmsad")
        )
        all_bmsad.sort()

        nested_bmsad.clear()
        nested_bmsad.update(split_directories(all_bmsad))

        all_bmsad_actordefs.clear()
        all_bmsad_actordefs.extend(f"actordef:{asset_name}" for asset_name in all_bmsad)

        file_browser = FileBrowser(pkg_editor)

        global_preferences["last_romfs"] = str(path)
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

                if file_browser is None:
                    imgui.text_disabled('Open file browser')
                else:
                    file_browser.menu_item()

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

            if imgui.begin_menu("BMSAD", len(nested_bmsad) > 0):
                def recursive_draw_menu(nested):
                    for key, value in nested.items():
                        if isinstance(value, str):
                            click, state = imgui.menu_item(key, "", value in open_bmsad)
                            if click:
                                if state:
                                    open_bmsad[value] = pkg_editor.get_parsed_asset(value)
                                else:
                                    open_bmsad.pop(value)
                        else:
                            if imgui.begin_menu(key, True):
                                recursive_draw_menu(value)
                                imgui.end_menu()

                recursive_draw_menu(nested_bmsad)

                imgui.end_menu()

            imgui.end_main_menu_bar()

        if current_level_data is not None:
            if not current_level_data.render_window(current_scale):
                current_level_data = None

        if current_level_data is not None:
            current_level_data.draw_visible_actors(current_scale)

        draw_open_bmsad(current_scale)
        if file_browser is not None and file_browser.is_open():
            file_browser.draw(current_scale, open_bmsad)

        imgui.show_test_window()

        gl.glClearColor(0, 0, 0, 1)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        imgui.render()
        impl.render(imgui.get_draw_data())
        glfw.swap_buffers(window)

        if pending_load_last_romfs and global_preferences.get("last_romfs") is not None:
            pending_load_last_romfs = False
            try:
                load_romfs(Path(global_preferences["last_romfs"]))
            except Exception as e:
                logging.exception(f"Unable to re-open last romfs: {e}")
                global_preferences["last_romfs"] = None
                save_preferences()

    impl.shutdown()
    glfw.terminate()


def main_loop():
    return loop()
