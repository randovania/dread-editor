import json
import re
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
from mercury_engine_data_structures.formats import Brfld
from mercury_engine_data_structures.game_check import Game
from mercury_engine_data_structures.pkg_editor import PkgEditor

all_types: Dict[str, dict] = {}
current_file: Optional[Brfld] = None
visible_actors: Dict[tuple[str, str], bool] = {}
preferences: Dict[str, typing.Any] = {}
preferences_file_path = Path(__file__).parent.joinpath("preferences.json")


def save_preferences():
    with preferences_file_path.open("w") as f:
        json.dump(preferences, f, indent=4)


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


def render_bool(value):
    imgui.text(str(value))


def render_float(value):
    imgui.text("{:.2f}".format(value))


def render_int(value):
    imgui.text(str(value))


def render_string(value):
    imgui.text(value)


def render_actor_link(value: str):
    if value.startswith("Root"):
        if imgui.button(value):
            if (actor := current_file.follow_link(value)) is not None:
                layer_name = value.split(":")[4]
                visible_actors[(layer_name, actor.sName)] = True
    else:
        imgui.text(value)


def render_float_vector(value):
    for i, it in enumerate(value):
        if i > 0:
            imgui.same_line()
        render_float(it)


_known_type_renders = {
    "bool": render_bool,
    "float": render_float,
    "float32": render_float,
    "int": render_int,
    "unsigned": render_int,
    "unsigned_int": render_int,

    "base::global::CStrId": render_string,
    "base::global::CFilePathStrId": render_string,
    "base::global::CRntString": render_string,
    "CGameLink<CActor>": render_actor_link,
    "CGameLink<CEntity>": render_actor_link,
    "CGameLink<CSpawnPointComponent>": render_actor_link,
    "base::global::CName": render_string,
    "base::core::CAssetLink": render_string,

    "base::math::CVector2D": render_float_vector,
    "base::math::CVector3D": render_float_vector,
    "base::math::CVector4D": render_float_vector,
}

vector_re = re.compile(r"(?:base::)?global::CRntVector<(.*?)(?:, false)?>$")
dict_re = re.compile(r"base::global::CRnt(?:Small)?Dictionary<base::global::CStrId,[\s_](.*)>$")

unique_ptr_re = re.compile(r"std::unique_ptr<(.*)>$")
weak_ptr_re = re.compile(r"base::global::CWeakPtr<(.*)>$")
raw_ptr_re = re.compile(r"(.*?)(?:[ ]?const)?\*$")
ref_re = re.compile(r"CGameObjectRef<(.*)>$")
typed_var_re = re.compile(r"(base::reflection::CTypedValue)$")
all_ptr_re = [unique_ptr_re, weak_ptr_re, raw_ptr_re, ref_re, typed_var_re]


def find_ptr_match(type_name: str):
    for expr in all_ptr_re:
        m = expr.match(type_name)
        if m is not None:
            return m


def render_vector_of_type(value: list, type_name: str, path: str):
    for i, item in enumerate(value):
        if i > 0:
            imgui.separator()
        render_value_of_type(item, type_name, f"{path}[{i}]")


def render_dict_of_type(value: dict, type_name: str, path: str):
    for key, item in value.items():
        if imgui.tree_node(f"{key} ##{path}[{key}]"):
            render_value_of_type(item, type_name, f"{path}[{key}]")
            imgui.tree_pop()


def render_ptr_of_type(value, type_name: str, path: str):
    if isinstance(value, dict) and "@type" in value:
        type_name = value["@type"]
    render_value_of_type(value, type_name, path)


def render_value_of_type(value, type_name: str, path: str):
    if type_name in _known_type_renders:
        _known_type_renders[type_name](value)

    elif (m := vector_re.match(type_name)) is not None:
        render_vector_of_type(value, m.group(1), path)

    elif (m := dict_re.match(type_name)) is not None:
        render_dict_of_type(value, m.group(1), path)

    elif (m := find_ptr_match(type_name)) is not None:
        render_ptr_of_type(value, m.group(1), path)

    elif type_name in all_types:
        def render_type(type_data):
            if type_data["parent"] is not None:
                render_type(all_types[type_data["parent"]])

            for field_name, field_type in type_data["fields"].items():
                if field_name in value:
                    if field_type in _known_type_renders:
                        imgui.text(field_name)
                        imgui.next_column()
                        render_value_of_type(value[field_name], field_type, f"{path}.{field_name}")
                        imgui.next_column()
                    else:
                        if imgui.tree_node(f"{field_name} ##{path}.{field_name}", imgui.TREE_NODE_DEFAULT_OPEN):
                            render_value_of_type(value[field_name], field_type, f"{path}.{field_name}")
                            imgui.tree_pop()
                        imgui.next_column()
                        imgui.next_column()

        if "@type" in value:
            imgui.text(f'Type: {value["@type"]}')
            imgui.next_column()
            imgui.next_column()
        render_type(all_types[type_name])

    else:
        print(f"Unsupported render of type {type_name}")




def loop():
    imgui.create_context()
    window = impl_glfw_init()
    impl = GlfwRenderer(window)

    global preferences, current_file, visible_actors
    if preferences_file_path.exists():
        preferences = json.loads(preferences_file_path.read_text())

    pkg_editor: Optional[PkgEditor] = None
    current_file_name: Optional[str] = None
    possible_brfld = []
    visible_actors = {}

    global all_types
    all_types_path = Path(r"C:\Users\henri\programming\mercury-engine-data-structures\tools\all_types.json")
    all_types = json.loads(all_types_path.read_text())

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
            possible_brfld.sort()
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
                index = -1
                if current_file_name is not None:
                    index = possible_brfld.index(current_file_name)
                changed, current = imgui.listbox("File to open", index, possible_brfld)
                if changed:
                    current_file_name = possible_brfld[current]
                    current_file = Brfld.parse(pkg_editor.get_asset_with_name(current_file_name),
                                               target_game=Game.DREAD)
                    visible_actors = {}
                imgui.end()

            if current_file is not None:
                imgui.begin(f"Actors: {current_file_name}", True)
                for layer_name in current_file.raw.Root.pScenario.rEntitiesLayer.dctSublayers:
                    if imgui.tree_node(layer_name):
                        for actor_name, actor in current_file.actors_for_layer(layer_name).items():
                            key = (layer_name, actor_name)
                            visible_actors[key] = imgui.checkbox(
                                f"{actor_name} ##{layer_name}_{actor_name}", visible_actors.get(key)
                            )[1]
                        imgui.tree_pop()
                imgui.end()

            for (layer_name, actor_name), active in visible_actors.items():
                if not active:
                    continue

                active = imgui.begin(f"Actor: {layer_name} - {actor_name}", active)[1]
                if not active:
                    visible_actors[(layer_name, actor_name)] = False
                    imgui.end()
                    continue

                actor = current_file.actors_for_layer(layer_name)[actor_name]
                imgui.columns(2)
                render_value_of_type(actor, actor["@type"], f"{layer_name}.{actor_name}")
                imgui.columns(1)

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
