import re

import imgui
from mercury_engine_data_structures import dread_types


def render_bool(value):
    imgui.text(str(value))


def render_float(value):
    imgui.text("{:.2f}".format(value))


def render_int(value):
    imgui.text(str(value))


def render_string(value):
    imgui.text(value)


def render_float_vector(value):
    [None, None, imgui.input_float2, imgui.input_float3, imgui.input_float4][len(value)]("", *value)


KNOWN_TYPE_RENDERS = {
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

    "base::math::CVector2D": render_float_vector,
    "base::math::CVector3D": render_float_vector,
    "base::math::CVector4D": render_float_vector,
}
vector_re = re.compile(r"(?:base::)?global::CRntVector<(.*?)(?:, false)?>$")
dict_re = re.compile(r"base::global::CRnt(?:Small)?Dictionary<base::global::CStrId,[\s_](.*)>$")
unique_ptr_re = re.compile(r"std::unique_ptr<(.*)>$")
weak_ptr_re = re.compile(r"base::global::CWeakPtr<(.*)>$")
raw_ptr_re = re.compile(r"(.*?)(?:[ ]?const)?\*$")
ref_re = re.compile(r"CGameObjectRef<(.*)>$")
typed_var_re = re.compile(r"(base::reflection::CTypedValue)$")
all_ptr_re = [unique_ptr_re, weak_ptr_re, raw_ptr_re, ref_re, typed_var_re]


def find_ptr_match(type_name: str):
    for expr in all_ptr_re:
        m = expr.match(type_name)
        if m is not None:
            return m


def render_vector_of_type(value: list, type_name: str, path: str):
    for i, item in enumerate(value):
        if i > 0:
            imgui.separator()
        render_value_of_type(item, type_name, f"{path}[{i}]")


def render_dict_of_type(value: dict, type_name: str, path: str):
    for key, item in value.items():
        if imgui.tree_node(f"{key} ##{path}[{key}]"):
            render_value_of_type(item, type_name, f"{path}[{key}]")
            imgui.tree_pop()


def render_ptr_of_type(value, type_name: str, path: str):
    if isinstance(value, dict) and "@type" in value:
        type_name = value["@type"]
    render_value_of_type(value, type_name, path)


def render_value_of_type(value, type_name: str, path: str):
    if type_name in KNOWN_TYPE_RENDERS:
        KNOWN_TYPE_RENDERS[type_name](value)

    elif (m := vector_re.match(type_name)) is not None:
        render_vector_of_type(value, m.group(1), path)

    elif (m := dict_re.match(type_name)) is not None:
        render_dict_of_type(value, m.group(1), path)

    elif (m := find_ptr_match(type_name)) is not None:
        render_ptr_of_type(value, m.group(1), path)

    elif type_name in dread_types.get():
        def render_type(type_data):
            if type_data["parent"] is not None:
                render_type(dread_types.get()[type_data["parent"]])

            for field_name, field_type in type_data["fields"].items():
                if field_name in value:
                    if field_type in KNOWN_TYPE_RENDERS:
                        imgui.text(field_name)
                        imgui.next_column()
                        render_value_of_type(value[field_name], field_type, f"{path}.{field_name}")
                        imgui.next_column()
                    else:
                        if imgui.tree_node(f"{field_name} ##{path}.{field_name}", imgui.TREE_NODE_DEFAULT_OPEN):
                            render_value_of_type(value[field_name], field_type, f"{path}.{field_name}")
                            imgui.tree_pop()
                        imgui.next_column()
                        imgui.next_column()

        if "@type" in value:
            imgui.text(f'Type: {value["@type"]}')
            imgui.next_column()
            imgui.next_column()
        render_type(dread_types.get()[type_name])

    else:
        print(f"Unsupported render of type {type_name}")
