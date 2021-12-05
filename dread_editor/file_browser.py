import imgui


class FileBrowser:
    _is_open: bool = False

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

        def draw_tree(body: dict):
            for name, contents in body.items():
                if isinstance(contents, dict):
                    if imgui.tree_node(name):
                        draw_tree(contents)
                        imgui.tree_pop()
                else:
                    imgui.text(name)

        draw_tree(self.all_files_tree)
        imgui.end()
        return
