import collections
import re
import typing

import imgui
from mercury_engine_data_structures import dread_data
from mercury_engine_data_structures.formats import dread_types

from dread_editor import imgui_util

ALL_TYPES = typing.cast(dict[str, dict[str, typing.Any]], dread_data.get_raw_types())
ALL_TYPES["CActor"]["read_only_fields"] = ["sName"]


def _calculate_type_children():
    result = collections.defaultdict(set)

    for type_name, type_data in ALL_TYPES.items():
        if type_data["parent"] is not None:
            result[type_data["parent"]].add(type_name)

    return dict(result)


TYPE_CHILDREN = _calculate_type_children()


def get_all_children_for(type_name: str):
    result = set()

    types_to_check = {type_name}
    while types_to_check:
        next_type = types_to_check.pop()

        if next_type in result:
            continue
        result.add(next_type)

        types_to_check.update(TYPE_CHILDREN.get(next_type, set()))

    return result


TEMPORARY_ACTORS = {}


def render_bool(value, path: str):
    return imgui.checkbox(f"##{path}", value)


def render_float(value, path: str):
    return imgui.drag_float(f"##{path}", value)


def render_int(value, path: str):
    return imgui.drag_int(f"##{path}", value)


def render_string(value, path: str):
    return imgui.input_text(f"##{path}", value, 500)


def render_float_vector(value, path: str):
    functions = [None, None, imgui.input_float2, imgui.input_float3, imgui.input_float4]
    return functions[len(value)](f"##{path}", *value)


def render_typed_value(value: bytes, path: str):
    imgui.text(str(value))
    if imgui.button(f"Read as CActor ##{path}"):
        TEMPORARY_ACTORS[path] = dread_types.CActor.parse(value)
    return False, value


KNOWN_TYPE_RENDERS: dict[str, typing.Callable[[typing.Any, str], tuple[bool, typing.Any]]] = {
    "bool": render_bool,
    "float": render_float,
    "float32": render_float,
    "int": render_int,
    "unsigned": render_int,
    "unsigned_int": render_int,

    "base::global::CStrId": render_string,
    "base::global::CFilePathStrId": render_string,
    "base::global::CRntString": render_string,
    "base::global::CName": render_string,
    "base::core::CAssetLink": render_string,
    "base::reflection::CTypedValue": render_typed_value,

    "base::math::CVector2D": render_float_vector,
    "base::math::CVector3D": render_float_vector,
    "base::math::CVector4D": render_float_vector,
}
KNOWN_TYPE_DEFAULTS: dict[str, typing.Callable[[], typing.Any]] = {
    "bool": lambda: False,
    "float": lambda: 0.0,
    "float32": lambda: 0.0,
    "int": lambda: 0,
    "unsigned": lambda: 0,
    "unsigned_int": lambda: 0,

    "base::global::CStrId": lambda: "",
    "base::global::CFilePathStrId": lambda: "",
    "base::global::CRntString": lambda: "",
    "base::global::CName": lambda: "",
    "base::core::CAssetLink": lambda: "<EMPTY>",
    "base::reflection::CTypedValue": lambda: b"",

    "base::math::CVector2D": lambda: [0.0, 0.0],
    "base::math::CVector3D": lambda: [0.0, 0.0, 0.0],
    "base::math::CVector4D": lambda: [0.0, 0.0, 0.0, 0.0],
}

vector_re = re.compile(r"(?:base::)?global::CRntVector<(.*?)(?:, false)?>$")
dict_re = re.compile(r"base::global::CRnt(?:Small)?Dictionary<base::global::CStrId,[\s_](.*)>$")
unique_ptr_re = re.compile(r"std::unique_ptr<(.*)>$")
weak_ptr_re = re.compile(r"base::global::CWeakPtr<(.*)>$")
raw_ptr_re = re.compile(r"(.*?)(?:[ ]?const)?\*$")
ref_re = re.compile(r"CGameObjectRef<(.*)>$")
typed_var_re = re.compile(r"(base::reflection::CTypedValue)$")
all_ptr_re = [unique_ptr_re, weak_ptr_re, raw_ptr_re, ref_re]


def find_ptr_match(type_name: str):
    for expr in all_ptr_re:
        m = expr.match(type_name)
        if m is not None:
            return m


def _render_container_of_type(value, type_name: str, path: str,
                              tree_node_flags,
                              iterate_func,
                              naming_func,
                              new_item_prompt_func,
                              delete_func,
                              ):
    modified = False
    single_column_element = type_uses_one_column(type_name)

    key_to_delete = None

    for key, item in iterate_func(value):
        element_path = f"{path}[{key}]"
        changed, result = False, item

        delete = imgui.button(f"X##{element_path}_delete")
        imgui.same_line()

        if single_column_element:
            imgui.text(naming_func(key))
            imgui.next_column()
            changed, result = render_value_of_type(item, type_name, element_path)
            imgui.next_column()
        else:
            node_open = imgui.tree_node(f"{naming_func(key)} ##{element_path}", tree_node_flags)
            if imgui.is_item_hovered():
                imgui.set_tooltip(type_name)

            imgui.next_column()
            imgui.next_column()
            if node_open:
                changed, result = render_value_of_type(item, type_name, element_path)
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
        new_element_func(create_default_of_type(type_name))
        modified = True

    return modified, value


def render_vector_of_type(value: list, type_name: str, path: str):
    def new_item_prompt():
        return imgui.button("New Item"), value.append

    return _render_container_of_type(
        value, type_name, path,
        imgui.TREE_NODE_DEFAULT_OPEN,
        lambda v: enumerate(v),
        lambda k: f"Item {k}",
        new_item_prompt,
        value.pop,
    )


def render_dict_of_type(value: dict, type_name: str, path: str):
    def new_item_prompt():
        _, key_name = imgui_util.persistent_input_text("", f"{path}_new_item", initial_value="Key")
        imgui.same_line()

        def item_add(new_item):
            value[key_name] = new_item

        return imgui.button("New Item"), item_add

    return _render_container_of_type(
        value, type_name, path,
        0,
        lambda v: v.items(),
        lambda k: k,
        new_item_prompt,
        value.pop,
    )


_debug_once = set()


def print_once(path, msg):
    if path not in _debug_once:
        _debug_once.add(path)
        print(msg)


def render_ptr_of_type(value, type_name: str, path: str):
    all_options = sorted(get_all_children_for(type_name))
    all_options.insert(0, "None")

    if value is None:
        value_type = "None"

    elif isinstance(value, dict) and "@type" in value:
        value_type = value["@type"]

    else:
        if len(all_options) != 2:
            imgui.text("Expected just two options.")
            imgui.next_column()
            imgui.next_column()
            return False, value

        value_type = all_options[1]

    if type_uses_one_column(type_name):
        print_once(path, f"At {path}, a ptr to single-column type {type_name}")

        # Type selector
        changed, selected = imgui_util.combo_str("##" + path, value_type, all_options)
        imgui.next_column()

        if changed:
            value_type = selected
            value = create_default_of_type(value_type)

        # Value
        result = value

        if value_type == "None":
            imgui.text("None")
        else:
            if not type_uses_one_column(value_type):
                imgui.text(f"Expected type {value_type} to use one column")
            else:
                value_changed, result = render_value_of_type(value, value_type, f"{path}.Deref")
                changed = changed or value_changed

        imgui.next_column()
        return changed, result
    else:
        imgui.text("Type")
        imgui.next_column()
        changed, selected = imgui_util.combo_str("##" + path, value_type, all_options)
        imgui.next_column()

        if changed:
            value_type = selected
            value = create_default_of_type(value_type)

        if value_type != "None":
            value_changed, value = render_value_of_type(value, value_type, f"{path}.Deref")
            changed = changed or value_changed

        return changed, value


def type_uses_one_column(type_name: str):
    if type_name in KNOWN_TYPE_RENDERS:
        return True

    if (m := vector_re.match(type_name)) is not None:
        return False

    if (m := dict_re.match(type_name)) is not None:
        return False

    if (m := find_ptr_match(type_name)) is not None:
        return False

    if type_name in ALL_TYPES:
        return ALL_TYPES[type_name]["values"] is not None

    # FIXME: unknown, so kind of logging would be nice
    return True


def create_default_of_type(type_name: str):
    if type_name in KNOWN_TYPE_DEFAULTS:
        return KNOWN_TYPE_DEFAULTS[type_name]()

    if (m := vector_re.match(type_name)) is not None:
        return []

    if (m := dict_re.match(type_name)) is not None:
        return {}

    if (m := find_ptr_match(type_name)) is not None:
        return None

    if type_name in ALL_TYPES:
        type_data = ALL_TYPES[type_name]
        if type_data["values"] is not None:
            # enum
            return "Invalid"
        else:
            # struct, empty struct is always nice :)
            return {"@type": type_name}

    # FIXME: unknown, so kind of logging would be nice
    return None


def render_enum_of_type(value: str, type_name: str, path: str) -> tuple[bool, typing.Any]:
    all_enum_values = list(ALL_TYPES[type_name]["values"].keys())
    changed, selected = imgui_util.combo_str("##" + path, value, all_enum_values)
    if changed:
        return True, selected
    else:
        return False, value


def render_value_of_type(value, type_name: str, path: str) -> tuple[bool, typing.Any]:
    if type_name in KNOWN_TYPE_RENDERS:
        return KNOWN_TYPE_RENDERS[type_name](value, path)

    if (m := vector_re.match(type_name)) is not None:
        return render_vector_of_type(value, m.group(1), path)

    if (m := dict_re.match(type_name)) is not None:
        return render_dict_of_type(value, m.group(1), path)

    if (m := find_ptr_match(type_name)) is not None:
        return render_ptr_of_type(value, m.group(1), path)

    if type_name not in ALL_TYPES:
        imgui.next_column()
        imgui.text(f"Unsupported render of type {type_name}")
        imgui.next_column()
        return False, value

    this_type = ALL_TYPES[type_name]

    if this_type.get("values") is not None:
        return render_enum_of_type(value, type_name, path)

    modified = False

    def render_type(current_type_name: str):
        nonlocal modified

        type_data = ALL_TYPES[current_type_name]

        if type_data["parent"] is not None:
            render_type(type_data["parent"])

        for field_name, field_type in type_data["fields"].items():
            field_path = f"{path}.{field_name}"
            tooltip = f"Field of class {current_type_name} of type {field_type}."

            field_present = field_name in value
            present_changed, field_present = imgui.checkbox(f"##{field_path}_present", field_present)
            imgui.same_line()

            if present_changed:
                modified = True
                if field_present:
                    value[field_name] = create_default_of_type(field_type)
                else:
                    value.pop(field_name)

            field_value = value.get(field_name)
            changed, new_field = False, field_value

            if type_uses_one_column(field_type) or not field_present:
                imgui.text(field_name)
                imgui_util.set_hovered_tooltip(tooltip)
                imgui.next_column()

                if field_present:
                    if field_name in type_data.get("read_only_fields", []):
                        imgui.text(str(field_value))
                    else:
                        changed, new_field = render_value_of_type(field_value, field_type, field_path)
                else:
                    imgui.text("<not defined>")

                imgui.next_column()
            else:
                node_open = imgui.tree_node(f"{field_name} ##{field_path}", imgui.TREE_NODE_DEFAULT_OPEN)
                imgui_util.set_hovered_tooltip(tooltip)

                imgui.next_column()
                imgui.next_column()
                if node_open:
                    changed, new_field = render_value_of_type(field_value, field_type, field_path)
                    imgui.tree_pop()

            if changed:
                value[field_name] = new_field
                modified = True

    render_type(type_name)
    return modified, value
