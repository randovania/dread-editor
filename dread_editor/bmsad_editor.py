import construct
import imgui
from mercury_engine_data_structures import type_lib
from mercury_engine_data_structures.file_tree_editor import FileTreeEditor
from mercury_engine_data_structures.formats import Bmsad
from mercury_engine_data_structures.formats.bmsad import find_charclass_for_type

from dread_editor import imgui_util
from dread_editor.file_editor import FileEditor
from dread_editor.type_render import TypeTreeRender

bmsad_tree_render = TypeTreeRender()


class BmsadEditor(FileEditor):
    def __init__(self, bmsad: Bmsad):
        self.bmsad = bmsad
        self.string_vector = type_lib.get_type("base::global::CRntVector<base::global::CStrId>")

    def is_modified(self):
        return False

    def save_modifications(self, pkg_editor: FileTreeEditor, path: str):
        pass

    def draw(self, current_scale: float):

        imgui.columns(2, "bmsad details")
        imgui.text("Name")
        imgui.next_column()
        imgui.text(self.bmsad.raw.name)
        imgui.next_column()

        imgui.text("Type")
        imgui.next_column()
        imgui.text(self.bmsad.raw.type)
        imgui.next_column()

        imgui.separator()
        prop = self.bmsad.raw.property

        imgui.text("Model Name")
        imgui.next_column()
        imgui.text(prop.model_name)
        imgui.next_column()

        node_open = imgui.tree_node("Sub Actors", imgui.TREE_NODE_DEFAULT_OPEN)
        imgui.next_column()
        imgui.next_column()
        if node_open:
            changed, new_field = bmsad_tree_render.render_value_of_type(prop.sub_actors, self.string_vector,
                                                                        "sub_actors")
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
                        if imgui_util.tree_node_with_column(f"Fields ##{component_key}_fields",
                                                            imgui.TREE_NODE_DEFAULT_OPEN):

                            if component.fields is not None:
                                fields = component.fields.fields
                            else:
                                fields = construct.Container()

                            changed, new_field = bmsad_tree_render.render_value_of_type(
                                fields,
                                type_lib.get_type(find_charclass_for_type(component.type)),
                                f"{component_key}"
                            )
                            if changed:
                                if component.fields is None:
                                    component.fields = construct.Container(
                                        empty_string="",
                                        root="Root",
                                        fields=new_field,
                                    )
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
            imgui.text(str(self.bmsad.raw))
            imgui.tree_pop()
