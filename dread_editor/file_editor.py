import imgui
from mercury_engine_data_structures.formats import BaseResource
from mercury_engine_data_structures.type_lib import BaseType

from dread_editor.type_render import TypeTreeRender


class FileEditor:
    def draw(self, current_scale: float):
        raise NotImplementedError()


class GenericEditor(FileEditor):
    def __init__(self, asset: BaseResource, tree_render: TypeTreeRender, asset_type: BaseType):
        self.asset = asset
        self.asset_type = asset_type
        self.tree_render = tree_render

    def draw(self, current_scale: float):
        imgui.columns(2, "actor details")
        self.tree_render.render_value_of_type(
            self.asset.raw.Root, self.asset_type,
            f"name",
        )
        imgui.columns(1, "actor details")
