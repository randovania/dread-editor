import colorsys
import copy
import hashlib
import os
import struct
import typing

import imgui
from mercury_engine_data_structures.file_tree_editor import FileTreeEditor, Game
from mercury_engine_data_structures.formats import Bmscc, Bmsld
from mercury_engine_data_structures.formats.bmsld import ProperActor
from mercury_engine_data_structures.type_lib import BaseType, get_type_lib_samus_returns

from dread_editor import imgui_util
from dread_editor.actor_filter import ActorFilter
from dread_editor.level_data_common import GameLinkRender, LevelData
from dread_editor.preferences import global_preferences, save_preferences
from dread_editor.type_render import TypeTreeRender, SpecificTypeRender


def get_subareas(pkg_editor: FileTreeEditor, bmsld_path: str) -> set[str]:
    cams: set[str] = set()

    bmscc = typing.cast(Bmscc, pkg_editor.get_parsed_asset(bmsld_path.replace(".bmsld", ".bmscc")))

    for subarea in bmscc.raw.layers[0].entries:
        cams.add(subarea.name)

    return cams


class LevelDataSR(LevelData):
    def __init__(self, file_name: str, bmsld: Bmsld, bmscc: Bmscc, valid_cameras: dict[str, bool],
                 display_borders: dict[str, float]):

        self.preferences = global_preferences.get(file_name, {})
        global_preferences[file_name] = self.preferences
        self.preferences["layers"] = self.preferences.get("layers", {})

        self.file_name = file_name
        self.bmsld = bmsld
        self.bmscc = bmscc
        self.visible_actors = {}
        self.valid_cameras = valid_cameras
        self.display_borders = display_borders
        self.highlighted_actors_in_canvas = []
        self.actor_filter = ActorFilter()
        self.copy_actor_name = ""
        self.type_lib = get_type_lib_samus_returns()

        self.tree_render = TypeTreeRender(self.type_lib)
        for k in ["CGameLink<ProperActor>", "CGameLink<CEntity>"]:
            self.tree_render.specific_renders[k] = GameLinkRender(self)

        self.tree_render.specific_renders["base::global::CRntFile"] = InnerValueRenderSR(self)

        for layer_index in range(len(bmsld.raw.actors)):
            if layer_index not in self.visible_layers:
                self.visible_layers[str(layer_index)] = True

    @classmethod
    def open_file(cls, pkg_editor: FileTreeEditor, file_name: str):
        bmsld = typing.cast(Bmsld, pkg_editor.get_parsed_asset(file_name))

        valid_cameras = {
            key: True
            for key in sorted(get_subareas(pkg_editor, file_name))
        }
        bmscc = typing.cast(Bmscc, pkg_editor.get_parsed_asset(file_name.replace(".bmsld", ".bmscc")))

        display_borders: dict[str, float] = {"left": 0, "right": 0, "top": 0, "bottom": 0}
        for entry in bmscc.raw.layers[0].entries:
            x1, y1, x2, y2 = entry.data.total_boundings
            if abs(x1) > 59999 or abs(y1) > 59999 or abs(x2) > 59999 or abs(y2) > 59999:
                if entry.name in valid_cameras:
                    valid_cameras.pop(entry.name)
                continue
            display_borders["left"] = min(display_borders["left"], x1)
            display_borders["bottom"] = min(display_borders["bottom"], y1)
            display_borders["right"] = max(display_borders["right"], x2)
            display_borders["top"] = max(display_borders["top"], y2)

        return cls(file_name, bmsld, bmscc, valid_cameras, display_borders)

    @property
    def visible_layers(self) -> dict[str, bool]:
        return self.preferences["layers"]

    @property
    def render_scale(self):
        return self.preferences.get("render_scale", 500.0)

    @render_scale.setter
    def render_scale(self, value):
        self.preferences["render_scale"] = value
        save_preferences()

    def open_actor_link(self, link: str):
        if (actor := self.bmsld.follow_link(link)) is not None:
            layer_name = link.split(":")[4]
            print(actor)
            self.visible_actors[(layer_name, actor.sName)] = True

    def render_actor_context_menu(self, layer_name: str, actor):
        if self.copy_actor_name is None:
            self.copy_actor_name = f"{actor.sName}_Copy"

        if imgui.button("Duplicate Actor"):
            new_actor = copy.deepcopy(actor)
            new_actor.sName = self.copy_actor_name
            self.add_new_actor(layer_name, new_actor)
            imgui.close_current_popup()
            self.copy_actor_name = None

        imgui.same_line()
        self.copy_actor_name = imgui.input_text(
            "New actor name",
            self.copy_actor_name or "",
            500
        )[1]

        imgui.text("Position:")
        imgui.same_line()
        changed_x, x = imgui.slider_float("##actor-context-position-x", actor.vPos[0],
                                          self.display_borders["left"], self.display_borders["right"])
        imgui.same_line()
        changed_y, y = imgui.slider_float("##actor-context-position-y", actor.vPos[1],
                                          self.display_borders["top"], self.display_borders["bottom"])
        if changed_x or changed_y:
            actor.vPos = (x, y, actor.vPos[2])

    def add_new_actor(self, layer_name: str, actor):
        if actor is not None:
            self.bmsld.actors_for_layer(layer_name)[actor.sName] = actor
            self.visible_actors[(layer_name, actor.sName)] = True

    def render_window(self, current_scale):
        imgui.set_next_window_size(900 * current_scale, 300 * current_scale, imgui.FIRST_USE_EVER)
        expanded, opened = imgui.begin(os.path.basename(self.file_name), True)

        if not opened:
            imgui.end()
            return False

        def color_for_layer(name: str):
            d = hashlib.blake2b(name.encode("utf-8"), digest_size=4).digest()
            d = struct.unpack("=L", d)[0] / 0xFFFFFFFF
            r, g, b = colorsys.hsv_to_rgb(d, 1, 1)
            return [r, g, b, 1]

        highlighted_actors_in_list = set()

        with imgui_util.with_group():
            imgui.text("Actor Layers")
            with imgui_util.with_child("##ActorLayers", 300 * current_scale, 0,
                                       imgui.WINDOW_ALWAYS_VERTICAL_SCROLLBAR):
                self.actor_filter.draw(current_scale)
                imgui.columns(2, "actor layers")
                imgui.set_column_width(-1, 20 * current_scale)
                for layer_index in range(len(self.bmsld.raw.actors)):
                    layer_name = str(layer_index)
                    changed, self.visible_layers[layer_name] = imgui.checkbox(f"##{layer_name}_visible",
                                                                              self.visible_layers[layer_name])
                    if changed:
                        save_preferences()

                    imgui.next_column()
                    if imgui_util.colored_tree_node(layer_name, color_for_layer(layer_name)):
                        actors = self.bmsld.raw.actors[int(layer_name)]

                        for actor_name, actor in actors.items():
                            key = (layer_name, actor_name)
                            if not self.actor_filter.passes(actor):
                                continue

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

                            if imgui.begin_popup_context_item():
                                self.render_actor_context_menu(layer_name, actor)
                                imgui.end_popup()

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
            changed, new_scale = imgui.slider_float("Scale", self.render_scale, 100, 1000)
            if changed:
                self.render_scale = new_scale

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
                                           flags=imgui.DRAW_CLOSED,
                                           thickness=5)
                else:
                    draw_list.add_polyline(raw_vertices, imgui.get_color_u32_rgba(0.2, 0.2, 1, 0.8),
                                           flags=imgui.DRAW_CLOSED,
                                           thickness=3)

            self.highlighted_actors_in_canvas = []

            for layer_index in range(len(self.bmsld.raw.actors)):
                layer_name = str(layer_index)
                if not self.visible_layers[layer_name]:
                    continue

                color = imgui.get_color_u32_rgba(*color_for_layer(layer_name))
                for actor_name in self.bmsld.raw.actors[layer_index]:
                    actor = self.bmsld.raw.actors[layer_index][actor_name]
                    if "x" not in actor:
                        # TODO: vPos might be a required field. Re-visit after editor fields
                        continue

                    final_x = lerp_x(actor.x)
                    final_y = lerp_y(actor.y)
                    if (layer_name, actor_name) in highlighted_actors_in_list:
                        draw_list.add_circle_filled(final_x, final_y, 15, imgui.get_color_u32_rgba(1, 1, 1, 1))
                    else:
                        draw_list.add_circle_filled(final_x, final_y, 5, color)

                    if (mouse.x - final_x) ** 2 + (mouse.y - final_y) ** 2 < 5 * 5:
                        self.highlighted_actors_in_canvas.append((layer_name, actor_name))

            if self.highlighted_actors_in_canvas and imgui.is_window_hovered():
                imgui.begin_tooltip()
                for layer_name, actor_name in self.highlighted_actors_in_canvas:
                    imgui.text(f"{layer_name} - {actor_name}")
                    if imgui.is_mouse_double_clicked(0):
                        self.visible_actors[(layer_name, actor_name)] = True
                imgui.end_tooltip()

                if len(self.highlighted_actors_in_canvas) == 1:
                    layer_name, actor_name = self.highlighted_actors_in_canvas[0]
                    if imgui.is_mouse_released(1):
                        print("OPEN THE POPUP!", f"canvas_actor_context_{layer_name}_{actor_name}")
                        imgui.open_popup(f"canvas_actor_context_{layer_name}_{actor_name}")

            # for sub_areas in self.bmsld.raw.sub_areas:
            #     layer_name = sub_areas.name
            #     for actor in list(self.bmsld.actors_for_layer(layer_name).values()):
            #         if imgui.begin_popup(f"canvas_actor_context_{layer_name}_{actor.sName}",
            #                              imgui.WINDOW_ALWAYS_AUTO_RESIZE | imgui.WINDOW_NO_TITLE_BAR |
            #                              imgui.WINDOW_NO_SAVED_SETTINGS):
            #             self.render_actor_context_menu(layer_name, actor)
            #             imgui.end_popup()

        imgui.end()
        return True

    def draw_visible_actors(self, current_scale: float):
        for (layer_name, actor_name), active in list(self.visible_actors.items()):
            if not active:
                continue

            imgui.set_next_window_size(300 * current_scale, 200 * current_scale, imgui.FIRST_USE_EVER)
            path = f"{self.file_name}_{layer_name}_{actor_name}"
            active = imgui.begin(f"Actor: {layer_name} - {actor_name} ##{path}", active)[1]
            if not active:
                self.visible_actors[(layer_name, actor_name)] = False
                imgui.end()
                continue

            actor = self.bmsld.raw.actors[int(layer_name)][actor_name]
            imgui.columns(2, "actor details")
            self.tree_render.render_value_of_type(
                actor, self.type_lib.get_type("ProperActor"),
                f"{self.file_name}.{layer_name}.{actor_name}",
            )
            imgui.columns(1, "actor details")

            imgui.separator()
            imgui.text("Actor Groups")

            with imgui_util.with_child("##ActorGroups", 0, 300 * current_scale,
                                       imgui.WINDOW_ALWAYS_VERTICAL_SCROLLBAR):
                for group_name in sorted(self.bmsld.all_actor_groups()):
                    changed, present = imgui.checkbox(f"{group_name} ##actor_group.{group_name}",
                                                      self.bmsld.is_actor_in_group(group_name, actor_name, layer_name))
                    # if changed:
                    #     if present:
                    #         self.bmsld.add_actor_to_group(group_name, actor_name, layer_name)
                    #     else:
                    #         self.bmsld.remove_actor_from_group(group_name, actor_name, layer_name)

            imgui.end()

    def apply_changes_to(self, pkg_editor: FileTreeEditor):
        pkg_editor.replace_asset(self.file_name, self.bmsld.build())
        # for actor in self.bmsld.all_actors():
        #     bmsad = actor.oActorDefLink.removeprefix("actordef:")
        #
        #     for pkg_name in pkg_editor.find_pkgs(self.file_name):
        #         pkg_editor.ensure_present(pkg_name, bmsad)

class InnerValueRenderSR(SpecificTypeRender):
    def __init__(self, level_data: LevelDataSR):
        self.level_data = level_data
        self.cache = {}

    def uses_one_column(self, type_data: BaseType):
        return False

    def create_default(self, type_data: BaseType):
        return b""

    def render_value(self, value: bytes, type_data: BaseType, path: str):
        if path not in self.cache:
            self.cache[path] = ProperActor.parse(value)

        result = value
        changed, new_actor = self.level_data.tree_render.render_value_of_type(
            self.cache[path], self.level_data.type_lib.get_type("ProperActor"),
            f"{path}.actor",
        )
        if changed:
            self.cache[path] = new_actor
            result = ProperActor.build(new_actor)

        return changed, result