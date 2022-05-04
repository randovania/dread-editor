import imgui
from mercury_engine_data_structures.file_tree_editor import FileTreeEditor
from mercury_engine_data_structures.formats import BaseResource
from mercury_engine_data_structures.type_lib import BaseType

from dread_editor.type_render import TypeTreeRender


class FileEditor:
    def draw(self, current_scale: float):
        raise NotImplementedError()

    def is_modified(self):
        raise NotImplementedError()

    def save_modifications(self, pkg_editor: FileTreeEditor, path: str):
        raise NotImplementedError()


class GenericEditor(FileEditor):
    def __init__(self, asset: BaseResource, tree_render: TypeTreeRender, asset_type: BaseType):
        self.asset = asset
        self.asset_type = asset_type
        self.tree_render = tree_render
        self.has_modifications = False

    def draw(self, current_scale: float):
        imgui.columns(2, "actor details")
        changed, new_value = self.tree_render.render_value_of_type(
            self.asset.raw.Root, self.asset_type,
            f"name",
        )
        if changed:
            self.asset.raw.Root = new_value
            self.has_modifications = changed

        imgui.columns(1, "actor details")

    def is_modified(self):
        return self.has_modifications

    def save_modifications(self, pkg_editor: FileTreeEditor, path: str):
        pkg_editor.replace_asset(
            path,
            self.asset.build(),
        )
        self.has_modifications = False
