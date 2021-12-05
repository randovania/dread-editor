import imgui


class FileBrowser:
    _is_open: bool = False
    filter: str = ""

    def __init__(self, all_files: list[str]):
        self.all_files_tree = {}

        for asset_name in all_files:
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

    def draw(self, current_scale: float):
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
                    if children_match_path(f"{parent_path}/{name}/", contents):
                        return True
                elif self.filter in f"{parent_path}/{name}":
                    return True

            return False

        def draw_tree(parent_path: str, body: dict):
            for name, contents in body.items():
                if isinstance(contents, dict):
                    path = f"{parent_path}/{name}/"
                    if not children_match_path(path, contents):
                        continue

                    if imgui.tree_node(name, imgui.TREE_NODE_DEFAULT_OPEN if len(contents) <= 1 else 0):
                        draw_tree(path, contents)
                        imgui.tree_pop()

                elif self.filter in f"{parent_path}/{name}":
                    imgui.text(name)

        draw_tree("", self.all_files_tree)
        imgui.end()
        return
