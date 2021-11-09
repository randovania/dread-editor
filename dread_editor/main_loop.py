import colorsys
import hashlib
import json
import os.path
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
from mercury_engine_data_structures import dread_data
from mercury_engine_data_structures.formats import Brfld, Brsa, Bmscc
from mercury_engine_data_structures.pkg_editor import PkgEditor

from dread_editor import type_render, imgui_util

preferences: Dict[str, typing.Any] = {}
preferences_file_path = Path("preferences.json")


def save_preferences():
    try:
        with preferences_file_path.open("w") as f:
            json.dump(preferences, f, indent=4)
    except IOError as e:
        print(f"Unable to save preferences: {e}")


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


def get_subareas(pkg_editor: PkgEditor, brfld_path: str) -> set[str]:
    cams: set[str] = set()

    brsa = typing.cast(Brsa, pkg_editor.get_parsed_asset(brfld_path.replace(".brfld", ".brsa")))

    for setup in brsa.raw.Root.pSubareaManager.vSubareaSetups:
        for config in setup.vSubareaConfigs:
            for cam in config.vsCameraCollisionsIds:
                cams.add(cam)

    return cams


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


class LevelData:
    def __init__(self, file_name: str, brfld: Brfld, bmscc: Bmscc, valid_cameras: dict[str, bool],
                 display_borders: dict[str, float]):
        self.file_name = file_name
        self.brfld = brfld
        self.bmscc = bmscc
        self.visible_actors = {}
        self.visible_layers = {layer_name: True for layer_name in brfld.all_layers()}
        self.valid_cameras = valid_cameras
        self.display_borders = display_borders
        self.render_scale = 500.0
        self.highlighted_actors_in_canvas = []

    @classmethod
    def open_file(cls, pkg_editor: PkgEditor, file_name: str):
        brfld = typing.cast(Brfld, pkg_editor.get_parsed_asset(file_name))

        valid_cameras = {
            key: True
            for key in sorted(get_subareas(pkg_editor, file_name))
        }
        bmscc = typing.cast(Bmscc, pkg_editor.get_parsed_asset(file_name.replace(".brfld", ".bmscc")))

        display_borders: dict[str, float] = {"left": 0, "right": 0, "top": 0, "bottom": 0}
        for entry in bmscc.raw.layers[0].entries:
            x1, y1, x2, y2 = entry.data.total_boundings
            if abs(x1) > 59999 or abs(y1) > 59999 or abs(x2) > 59999 or abs(y2) > 59999:
                if entry.name in valid_cameras:
                    print(f"Removing {entry.name} as valid camera, boudings: {entry.data.total_boundings}")
                    valid_cameras.pop(entry.name)
                continue
            display_borders["left"] = min(display_borders["left"], x1)
            display_borders["bottom"] = min(display_borders["bottom"], y1)
            display_borders["right"] = max(display_borders["right"], x2)
            display_borders["top"] = max(display_borders["top"], y2)

        return cls(file_name, brfld, bmscc, valid_cameras, display_borders)

    def open_actor_link(self, link: str):
        if (actor := self.brfld.follow_link(link)) is not None:
            layer_name = link.split(":")[4]
            self.visible_actors[(layer_name, actor.sName)] = True

    def render_window(self, current_scale):
        imgui.set_next_window_size(900 * current_scale, 300 * current_scale, imgui.FIRST_USE_EVER)
        expanded, opened = imgui.begin(os.path.basename(self.file_name), True)

        if not opened:
            imgui.end()
            return False

        def color_for_layer(name: str):
            d = hashlib.blake2b(name.encode("utf-8"), digest_size=4).digest()
            d = struct.unpack("L", d)[0] / 0xFFFFFFFF
            r, g, b = colorsys.hsv_to_rgb(d, 1, 1)
            return [r, g, b, 1]

        highlighted_actors_in_list = set()

        with imgui_util.with_group():
            imgui.text("Actor Layers")
            with imgui_util.with_child("##ActorLayers", 300 * current_scale, 0,
                                       imgui.WINDOW_ALWAYS_VERTICAL_SCROLLBAR):
                imgui.columns(2, "actor layers")
                imgui.set_column_width(-1, 20 * current_scale)
                for layer_name in self.brfld.raw.Root.pScenario.rEntitiesLayer.dctSublayers:
                    self.visible_layers[layer_name] = imgui.checkbox(f"##{layer_name}_visible",
                                                                     self.visible_layers[layer_name])[1]
                    imgui.next_column()
                    if imgui_util.colored_tree_node(layer_name, color_for_layer(layer_name)):
                        for actor_name, actor in self.brfld.actors_for_layer(layer_name).items():
                            key = (layer_name, actor_name)

                            def do_item():
                                self.visible_actors[key] = imgui.checkbox(
                                    f"{actor_name} ##{layer_name}_{actor_name}", self.visible_actors.get(key)
                                )[1]

                            if (layer_name, actor) in self.highlighted_actors_in_canvas:
                                with imgui.colored(imgui.COLOR_TEXT, 1, 1, 0.2):
                                    do_item()
                            else:
                                do_item()

                            if imgui.is_item_hovered():
                                highlighted_actors_in_list.add(key)
                        imgui.tree_pop()
                    imgui.next_column()
                imgui.columns(1, "actor layers")

        imgui.same_line()

        with imgui_util.with_group():
            imgui.text("Camera Groups")
            with imgui_util.with_child("##CameraSections", 200 * current_scale, 0,
                                       imgui.WINDOW_ALWAYS_VERTICAL_SCROLLBAR):
                highlighted_section = None
                for key in self.valid_cameras.keys():
                    self.valid_cameras[key] = imgui.checkbox(key, self.valid_cameras[key])[1]
                    if imgui.is_item_hovered():
                        highlighted_section = key

        imgui.same_line()

        with imgui_util.with_child("##Canvas", 0, 0):
            self.render_scale = imgui.slider_float("Scale", self.render_scale, 100, 1000)[1]
            self.display_borders["left"], self.display_borders["right"] = imgui.slider_float2(
                "Left and right borders",
                self.display_borders["left"],
                self.display_borders["right"],
                -59999,
                59999,
            )[1]
            self.display_borders["top"], self.display_borders["bottom"] = imgui.slider_float2(
                "Top and bottom borders",
                self.display_borders["top"],
                self.display_borders["bottom"],
                59999,
                -59999,
            )[1]

            imgui.separator()

            mouse = imgui.get_mouse_pos()
            canvas_po = imgui.get_cursor_screen_pos()
            actual_scale = self.render_scale * current_scale
            draw_list = imgui.get_window_draw_list()

            def lerp_x(x):
                lx = (x - self.display_borders["left"]) / (
                        self.display_borders["right"] - self.display_borders["left"])
                return lx * actual_scale + canvas_po.x

            def lerp_y(y):
                ly = (y - self.display_borders["top"]) / (
                        self.display_borders["bottom"] - self.display_borders["top"])
                return ly * actual_scale + canvas_po.y

            for entry in self.bmscc.raw.layers[0].entries:
                if not self.valid_cameras.get(entry.name):
                    continue

                raw_vertices = [
                    (lerp_x(v.x), lerp_y(v.y))
                    for v in entry.data.polys[0].points
                ]
                if highlighted_section == entry.name:
                    draw_list.add_polyline(raw_vertices, imgui.get_color_u32_rgba(0.2, 0.8, 1, 1.0),
                                           closed=True,
                                           thickness=5)
                else:
                    draw_list.add_polyline(raw_vertices, imgui.get_color_u32_rgba(0.2, 0.2, 1, 0.8),
                                           closed=True,
                                           thickness=3)

            self.highlighted_actors_in_canvas = []

            for layer_name in self.brfld.all_layers():
                if not self.visible_layers[layer_name]:
                    continue

                color = imgui.get_color_u32_rgba(*color_for_layer(layer_name))
                for actor in self.brfld.actors_for_layer(layer_name).values():
                    if "vPos" not in actor:
                        # TODO: vPos might be a required field. Re-visit after editor fields
                        continue

                    final_x = lerp_x(actor.vPos[0])
                    final_y = lerp_y(actor.vPos[1])
                    if (layer_name, actor.sName) in highlighted_actors_in_list:
                        draw_list.add_circle_filled(final_x, final_y, 15, imgui.get_color_u32_rgba(1, 1, 1, 1))
                    else:
                        draw_list.add_circle_filled(final_x, final_y, 5, color)

                    if (mouse.x - final_x) ** 2 + (mouse.y - final_y) ** 2 < 5 * 5:
                        self.highlighted_actors_in_canvas.append((layer_name, actor))

            if self.highlighted_actors_in_canvas:
                imgui.begin_tooltip()
                for layer_name, actor in self.highlighted_actors_in_canvas:
                    imgui.text(f"{layer_name} - {actor.sName}")
                imgui.end_tooltip()

        imgui.end()
        return True

    def draw_visible_actors(self, current_scale: float):
        for (layer_name, actor_name), active in self.visible_actors.items():
            if not active:
                continue

            imgui.set_next_window_size(300 * current_scale, 200 * current_scale, imgui.FIRST_USE_EVER)
            path = f"{self.file_name}_{layer_name}_{actor_name}"
            active = imgui.begin(f"Actor: {layer_name} - {actor_name} ##{path}", active)[1]
            if not active:
                self.visible_actors[(layer_name, actor_name)] = False
                imgui.end()
                continue

            actor = self.brfld.actors_for_layer(layer_name)[actor_name]
            imgui.columns(2, "actor details")
            type_render.render_value_of_type(actor, actor["@type"], f"{layer_name}.{actor_name}")
            imgui.columns(1, "actor details")

            imgui.end()

    def apply_changes_to(self, pkg_editor: PkgEditor):
        pkg_editor.replace_asset(self.file_name, self.brfld.build())


current_level_data: Optional[LevelData] = None


def render_actor_link(value: str, path: str):
    if value.startswith("Root") and current_level_data is not None:
        if imgui.button(value):
            current_level_data.open_actor_link(value)
    else:
        imgui.text(value)
    return False, None


for k in ["CGameLink<CActor>", "CGameLink<CEntity>", "CGameLink<CSpawnPointComponent>"]:
    type_render.KNOWN_TYPE_RENDERS[k] = render_actor_link


def loop():
    imgui.create_context()
    window = impl_glfw_init()
    impl = GlfwRenderer(window)

    global preferences, current_level_data
    if preferences_file_path.exists():
        preferences = json.loads(preferences_file_path.read_text())

    pkg_editor: Optional[PkgEditor] = None
    current_error_message = None
    possible_brfld = []

    with ExitStack() as stack:
        def load_romfs(path: Path):
            nonlocal pkg_editor, possible_brfld
            stack.close()
            pkg_editor = stack.enter_context(PkgEditor.open_pkgs_at(path))
            possible_brfld = [
                name
                for asset_id in pkg_editor.all_asset_ids()
                if (name := dread_data.name_for_asset_id(asset_id)) is not None
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

                    imgui.text_disabled(f'* Current root: {preferences.get("last_romfs")}')
                    imgui.separator()

                    if imgui.menu_item("Select output path")[0]:
                        f = prompt_file(directory=True)
                        if f:
                            preferences["output_path"] = f
                            save_preferences()

                    imgui.text_disabled(f'* Current output path: {preferences.get("output_path")}')
                    imgui.separator()

                    changed, new_value = imgui.checkbox("Read files from output path first",
                                                        preferences.get("read_output", False))
                    if changed:
                        preferences["read_output"] = new_value
                        save_preferences()

                    if imgui.menu_item("Save changes")[0]:
                        if pkg_editor is None:
                            current_error_message = "Unable to save, no root selected."
                        elif preferences.get("output_path") is None:
                            current_error_message = "Unable to save, no output path."
                        else:
                            if current_level_data is not None:
                                current_level_data.apply_changes_to(pkg_editor)
                            pkg_editor.save_modified_pkgs(Path(preferences["output_path"]))

                    imgui.end_menu()

                if imgui.begin_menu("Select level file", len(possible_brfld) > 0):
                    current_file_name = None
                    if current_level_data is not None:
                        current_file_name = current_level_data.file_name

                    for name in possible_brfld:
                        if imgui.menu_item(name, "", name == current_file_name)[0]:
                            current_level_data = LevelData.open_file(pkg_editor, name)

                    imgui.end_menu()

                imgui.end_main_menu_bar()

            if current_level_data is not None:
                if not current_level_data.render_window(current_scale):
                    current_level_data = None

            if current_level_data is not None:
                current_level_data.draw_visible_actors(current_scale)

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
