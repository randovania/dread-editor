import typing
import imgui

from dread_editor.type_render import SpecificTypeRender
from dread_editor import imgui_util
from mercury_engine_data_structures.type_lib import BaseType

class LevelData:
    def open_actor_link(self, link: str):
        raise NotImplementedError("Not implemented")


class GameLinkRender(SpecificTypeRender):
    def __init__(self, level_data: LevelData):
        self.level_data = level_data

    def uses_one_column(self, type_data: BaseType):
        return True

    def create_default(self, type_data: BaseType):
        return "<EMPTY>"

    def render_value(self, value: typing.Any, type_data: BaseType, path: str):
        if isinstance(value, str) and value.startswith("Root"):
            if imgui.button(value):
                self.level_data.open_actor_link(value)
            imgui_util.set_hovered_tooltip(value)
        else:
            imgui.text(str(value))
        return False, None


