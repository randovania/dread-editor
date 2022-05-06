import enum
import typing

import imgui
from mercury_engine_data_structures import type_lib
from mercury_engine_data_structures.type_lib import (
    TypeKind, VectorType, DictionaryType, PointerType,
    EnumType, StructType, PrimitiveType, PrimitiveKind,
    TypedefType, FlagsetType, BaseType
)

from dread_editor import imgui_util


def render_bool(value, path: str):
    return imgui.checkbox(f"##{path}", value)


def render_float(value, path: str):
    return imgui.drag_float(f"##{path}", value)


def render_int(value, path: str):
    try:
        return imgui.drag_int(f"##{path}", value)
    except OverflowError:
        imgui.text(str(value))
        return False, value


def render_string(value, path: str):
    return imgui.input_text(f"##{path}", value, 500)


def render_float_vector(value, path: str):
    functions = [None, None, imgui.input_float2, imgui.input_float3, imgui.input_float4]
    return functions[len(value)](f"##{path}", *value)


def render_unsupported_value(value, path: str):
    imgui.text(str(value))
    return False, value


class SpecificTypeRender:
    def uses_one_column(self, type_data: BaseType):
        raise NotImplementedError()

    def create_default(self, type_data: BaseType):
        raise NotImplementedError()

    def render_value(self, value: typing.Any, type_data: BaseType, path: str):
        raise NotImplementedError()


class ExprSpecificTypeRender(SpecificTypeRender):
    def __init__(self, uses_one_column, create_default, render_value):
        self._uses_one_column = uses_one_column
        self._create_default = create_default
        self._render_value = render_value

    def uses_one_column(self, type_data: BaseType):
        return self._uses_one_column()

    def create_default(self, type_data: BaseType):
        return self._create_default()

    def render_value(self, value: typing.Any, type_data: BaseType, path: str):
        return self._render_value(value, path)


PRIMITIVE_RENDERS = {
    PrimitiveKind.VECTOR_2: ExprSpecificTypeRender(lambda: True, lambda: [0.0, 0.0], render_float_vector),
    PrimitiveKind.VECTOR_3: ExprSpecificTypeRender(lambda: True, lambda: [0.0, 0.0, 0.0], render_float_vector),
    PrimitiveKind.VECTOR_4: ExprSpecificTypeRender(lambda: True, lambda: [0.0, 0.0, 0.0, 0.0], render_float_vector),
    PrimitiveKind.FLOAT: ExprSpecificTypeRender(lambda: True, lambda: 0.0, render_float),
    PrimitiveKind.INT: ExprSpecificTypeRender(lambda: True, lambda: 0, render_int),
    PrimitiveKind.STRING: ExprSpecificTypeRender(lambda: True, lambda: "", render_string),
    PrimitiveKind.UINT: ExprSpecificTypeRender(lambda: True, lambda: 0, render_int),
    PrimitiveKind.BOOL: ExprSpecificTypeRender(lambda: True, lambda: False, render_bool),
    PrimitiveKind.UINT_16: ExprSpecificTypeRender(lambda: True, lambda: 0, render_int),
    PrimitiveKind.UINT_64: ExprSpecificTypeRender(lambda: True, lambda: 0, render_int),
    PrimitiveKind.BYTES: ExprSpecificTypeRender(lambda: True, lambda: b"", render_unsupported_value),
    PrimitiveKind.PROPERTY: ExprSpecificTypeRender(lambda: True, lambda: 0, render_unsupported_value),
}


class TypeTreeRender:
    specific_renders: dict[str, SpecificTypeRender]

    def __init__(self):
        self._debug_once = set()
        self.memory = {}
        self.specific_renders = {}

    def print_once(self, path, msg):
        if path not in self._debug_once:
            self._debug_once.add(path)
            print(msg)

    def type_uses_one_column(self, type_data: BaseType):
        if (specific_render := self.specific_renders.get(type_data.name)) is not None:
            return specific_render.uses_one_column(type_data)

        if type_data.kind == TypeKind.PRIMITIVE:
            assert isinstance(type_data, PrimitiveType)
            return PRIMITIVE_RENDERS[type_data.primitive_kind].uses_one_column(type_data)

        if type_data.kind in {TypeKind.VECTOR, TypeKind.DICTIONARY, TypeKind.POINTER, TypeKind.STRUCT}:
            return False

        return True

    def create_default_of_type(self, type_data: BaseType):
        if (specific_render := self.specific_renders.get(type_data.name)) is not None:
            return specific_render.create_default(type_data)

        if isinstance(type_data, PrimitiveType):
            return PRIMITIVE_RENDERS[type_data.primitive_kind].create_default(type_data)

        elif isinstance(type_data, StructType):
            return {"@type": type_data.name}

        elif isinstance(type_data, EnumType):
            return "Invalid"

        elif isinstance(type_data, FlagsetType):
            # TODO
            return "Invalid"

        elif isinstance(type_data, TypedefType):
            raise ValueError(f"Unexpected typedef type: {type_data}")

        elif isinstance(type_data, PointerType):
            return None

        elif isinstance(type_data, VectorType):
            return []

        elif isinstance(type_data, DictionaryType):
            return {}

        else:
            raise ValueError(f"Unknown type_data: {type_data}")

    def _render_container_of_type(self, value, element_type: BaseType, path: str,
                                  tree_node_flags,
                                  iterate_func,
                                  naming_func,
                                  new_item_prompt_func,
                                  delete_func,
                                  ):
        modified = False
        single_column_element = self.type_uses_one_column(element_type)

        key_to_delete = None

        for key, item in iterate_func(value):
            element_path = f"{path}[{key}]"
            changed, result = False, item

            delete = imgui.button(f"X##{element_path}_delete")
            imgui.same_line()

            if single_column_element:
                imgui.text(naming_func(key))
                imgui.next_column()
                changed, result = self.render_value_of_type(item, element_type, element_path)
                imgui.next_column()
            else:
                node_open = imgui.tree_node(f"{naming_func(key)} ##{element_path}", tree_node_flags)
                if imgui.is_item_hovered():
                    imgui.set_tooltip(element_type.name)

                imgui.next_column()
                imgui.next_column()
                if node_open:
                    changed, result = self.render_value_of_type(item, element_type, element_path)
                    imgui.tree_pop()

            if delete:
                key_to_delete = key
                modified = True

            elif changed:
                value[key] = result
                modified = True

        if key_to_delete is not None:
            delete_func(key_to_delete)

        new_element, new_element_func = new_item_prompt_func()
        imgui.next_column()
        imgui.next_column()

        if new_element:
            new_element_func(self.create_default_of_type(element_type))
            modified = True

        return modified, value

    def render_vector_of_type(self, value: list, type_data: VectorType, path: str):
        def new_item_prompt():
            return imgui.button("New Item"), value.append

        return self._render_container_of_type(
            value, type_lib.get_type(type_data.value_type), path,
            imgui.TREE_NODE_DEFAULT_OPEN if len(value) < 50 else 0,
            lambda v: enumerate(v),
            lambda k: f"Item {k}",
            new_item_prompt,
            value.pop,
        )

    def render_dict_of_type(self, value: dict, type_data: DictionaryType, path: str):
        key_type = type_lib.get_type(type_data.key_type)

        if isinstance(key_type, PrimitiveType) and key_type.primitive_kind == PrimitiveKind.STRING:
            def new_item_prompt():
                _, key_name = imgui_util.persistent_input_text("", f"{path}_new_item", initial_value="Key")
                imgui.same_line()

                def item_add(new_item):
                    value[key_name] = new_item

                return imgui.button("New Item"), item_add

            return self._render_container_of_type(
                value, type_lib.get_type(type_data.value_type), path,
                0,
                lambda v: v.items(),
                lambda k: k,
                new_item_prompt,
                value.pop,
            )
        else:
            imgui.next_column()
            imgui.text(f"Unsupported render of dictionary with key {type_data.key_type}")
            imgui.next_column()
            return False, value

    def render_ptr_of_type(self, value, type_data: PointerType, path: str):
        all_options = sorted(type_lib.get_all_children_for(type_data.target))
        all_options.insert(0, "None")

        value_type_name: str

        if value is None:
            value_type_name = "None"

        elif isinstance(value, dict) and "@type" in value:
            value_type_name = value["@type"]

        else:
            if len(all_options) != 2:
                imgui.text("Expected just two options.")
                imgui.next_column()
                imgui.next_column()
                return False, value

            value_type_name = all_options[1]

        def create_default(type_name: str):
            if value_type_name == "None":
                return None
            else:
                return self.create_default_of_type(type_lib.get_type(value_type_name))

        # TODO: this check doesn't make sense
        if self.type_uses_one_column(type_data):
            self.print_once(path, f"At {path}, a ptr to single-column type {type_data.name}")

            # Type selector
            changed, selected = imgui_util.combo_str("##" + path, value_type_name, all_options)
            imgui.next_column()

            if changed:
                value_type_name = selected
                value = create_default(value_type_name)

            # Value
            result = value

            if value_type_name == "None":
                imgui.text("None")
            else:
                value_type_data = type_lib.get_type(value_type_name)
                if not self.type_uses_one_column(value_type_data):
                    imgui.text(f"Expected type {value_type_name} to use one column")
                else:
                    value_changed, result = self.render_value_of_type(value, value_type_data, f"{path}.Deref")
                    changed = changed or value_changed

            imgui.next_column()
            return changed, result
        else:
            imgui.text("Type")
            imgui.next_column()
            changed, selected = imgui_util.combo_str("##" + path, value_type_name, all_options)
            imgui.next_column()

            if changed:
                value_type_name = selected
                value = create_default(value_type_name)

            if value_type_name != "None":
                value_type_data = type_lib.get_type(value_type_name)
                value_changed, value = self.render_value_of_type(value, value_type_data, f"{path}.Deref")
                changed = changed or value_changed

            return changed, value

    def render_enum_of_type(self, value: enum.IntEnum, type_data: EnumType, path: str) -> tuple[bool, typing.Any]:
        changed, selected = imgui_util.combo_enum("##" + path, value, type_data.enum_class())
        if changed:
            return True, selected
        else:
            return False, value

    def render_flagset_of_type(self, value: dict, type_data: FlagsetType, path: str) -> tuple[bool, typing.Any]:
        enum_data = type_lib.get_type(type_data.enum)
        assert isinstance(enum_data, EnumType)

        changed, selected = imgui_util.combo_flagset(path, value, enum_data.enum_class())
        if changed:
            return True, selected
        else:
            return False, value

    def render_struct_of_type(self, value, type_data: StructType, path: str) -> tuple[bool, typing.Any]:
        modified = False

        if type_data.parent is not None:
            parent = type_lib.get_type(type_data.parent)
            assert isinstance(parent, StructType)
            modified, value = self.render_struct_of_type(value, parent, path)

        for field_name, field_type in type_data.fields.items():
            field_type_data = type_lib.get_type(field_type)

            field_path = f"{path}.{field_name}"
            tooltip = f"Field of class {type_data.name} of type {field_type_data.name}."

            field_present = field_name in value
            present_changed, field_present = imgui.checkbox(f"##{field_path}_present", field_present)
            imgui.same_line()

            if present_changed:
                modified = True
                if field_present:
                    value[field_name] = self.create_default_of_type(field_type_data)
                else:
                    value.pop(field_name)

            field_value = value.get(field_name)
            changed, new_field = False, field_value

            if self.type_uses_one_column(field_type_data) or not field_present:
                imgui.text(field_name)
                imgui_util.set_hovered_tooltip(tooltip)
                imgui.next_column()

                if field_present:
                    changed, new_field = self.render_value_of_type(field_value, field_type_data, field_path)
                else:
                    imgui.text("<not defined>")

                imgui.next_column()
            else:
                node_open = imgui.tree_node(f"{field_name} ##{field_path}",
                                            imgui.TREE_NODE_DEFAULT_OPEN
                                            if self.should_default_to_open(field_value, field_type_data, field_path)
                                            else 0)
                imgui_util.set_hovered_tooltip(tooltip)

                imgui.next_column()
                imgui.next_column()
                if node_open:
                    changed, new_field = self.render_value_of_type(field_value, field_type_data, field_path)
                    imgui.tree_pop()

            if changed:
                value[field_name] = new_field
                modified = True

        return modified, value

    def render_value_of_type(self, value, type_data: BaseType, path: str) -> tuple[bool, typing.Any]:
        if (specific_render := self.specific_renders.get(type_data.name)) is not None:
            return specific_render.render_value(value, type_data, path)

        if isinstance(type_data, PrimitiveType):
            return PRIMITIVE_RENDERS[type_data.primitive_kind].render_value(value, type_data, path)

        elif isinstance(type_data, StructType):
            return self.render_struct_of_type(value, type_data, path)

        elif isinstance(type_data, EnumType):
            return self.render_enum_of_type(value, type_data, path)

        elif isinstance(type_data, FlagsetType):
            return self.render_flagset_of_type(value, type_data, path)

        elif isinstance(type_data, TypedefType):
            raise ValueError(f"Unexpected typedef type: {type_data}")

        elif isinstance(type_data, PointerType):
            return self.render_ptr_of_type(value, type_data, path)

        elif isinstance(type_data, VectorType):
            return self.render_vector_of_type(value, type_data, path)

        elif isinstance(type_data, DictionaryType):
            return self.render_dict_of_type(value, type_data, path)

        else:
            raise ValueError(f"Unknown type_data: {type_data}")

    def should_default_to_open(self, value, type_data: BaseType, path: str) -> bool:
        if isinstance(type_data, VectorType):
            assert isinstance(value, list)
            return len(value) < 50
        return True
