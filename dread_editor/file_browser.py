import typing

import imgui
from mercury_engine_data_structures.type_lib_instances import get_type_lib_dread
from mercury_engine_data_structures.file_tree_editor import FileTreeEditor, Game
from mercury_engine_data_structures.formats import Bmsad

from dread_editor.bmsad_editor import BmsadEditor
from dread_editor.file_editor import FileEditor, GenericEditor
from dread_editor.type_render import TypeTreeRender


def create_editor_reader(type_name: str):
    type_lib = get_type_lib_dread()
    type_data = type_lib.get_type( type_name)
    return lambda path, tree_editor: GenericEditor(
        tree_editor.get_parsed_asset(path),
        TypeTreeRender(type_lib),
        type_data,
    )


file_types_dread = {
    ".bmsad": lambda path, tree_editor: BmsadEditor(tree_editor.get_parsed_asset(path, type_hint=Bmsad)),
    ".bmmap": create_editor_reader('CMinimapData'),
    ".bmscu": create_editor_reader('CCutSceneDef'),
    ".brsa": create_editor_reader("gameeditor::CGameModelRoot"),
}

file_types_sr = {
    ".bmsad": lambda path, tree_editor: BmsadEditor(tree_editor.get_parsed_asset(path, type_hint=Bmsad)),
}

file_types = {
    Game.SAMUS_RETURNS: file_types_sr,
    Game.DREAD: file_types_dread
}


class FileBrowser:
    _is_open: bool = False
    filter: str = ""

    def __init__(self, tree_editor: FileTreeEditor, game: Game):
        self.tree_editor = tree_editor
        self.all_files_tree = {}
        self.game = game

        for asset_name in sorted(tree_editor.all_asset_names()):
            name_tree = asset_name.split("/")
            parent = self.all_files_tree
            for segment in name_tree[:-1]:
                if segment not in parent:
                    parent[segment] = {}
                parent = parent[segment]
            parent[name_tree[-1]] = True

    def is_open(self):
        return self._is_open

    def menu_item(self):
        click, new_file_browser_state = imgui.menu_item("Open file browser", "", self._is_open)
        if click:
            self._is_open = new_file_browser_state

    def draw(self, current_scale: float, open_editors: dict[str, FileEditor]):
        active = imgui.begin("File Browser", True)[1]
        if not active:
            imgui.end()
            self._is_open = False
            return

        self.filter = imgui.input_text("Filter", self.filter, 500)[1]

        def children_match_path(parent_path: str, body: dict) -> bool:
            if self.filter in parent_path:
                return True

            for name, contents in body.items():
                if isinstance(contents, dict):
                    if children_match_path(f"{parent_path}{name}/", contents):
                        return True
                elif self.filter in f"{parent_path}{name}":
                    return True

            return False

        def draw_tree(parent_path: str, body: dict[str, typing.Any]):
            for name, contents in body.items():
                if isinstance(contents, dict):
                    path = f"{parent_path}{name}/"
                    if not children_match_path(path, contents):
                        continue

                    if imgui.tree_node(name, imgui.TREE_NODE_DEFAULT_OPEN if len(contents) <= 1 else 0):
                        draw_tree(path, contents)
                        imgui.tree_pop()

                elif self.filter in (full_name := f"{parent_path}{name}"):
                    imgui.text(name)

                    if imgui.begin_popup_context_item(f"##{full_name}"):
                        if imgui.button("Extract file"):
                            full_path = self.tree_editor.root.joinpath(full_name)
                            full_path.parent.mkdir(parents=True, exist_ok=True)
                            full_path.write_bytes(self.tree_editor.get_raw_asset(full_name))

                        for extension, build in file_types.get(self.game).items():
                            if name.endswith(extension):
                                if imgui.button("Open"):
                                    open_editors[full_name] = build(full_name, self.tree_editor)

                        imgui.end_popup()

        draw_tree("", self.all_files_tree)
        imgui.end()
        return
