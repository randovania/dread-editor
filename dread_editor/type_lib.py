import collections
import typing

from mercury_engine_data_structures import dread_data

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


def is_known_type(type_name: str) -> bool:
    return type_name in ALL_TYPES


def is_enum(type_name: str) -> bool:
    if type_name in ALL_TYPES:
        return ALL_TYPES[type_name]["values"] is not None
    return False


def is_struct(type_name: str) -> bool:
    if type_name in ALL_TYPES:
        return ALL_TYPES[type_name]["values"] is None
    return False


def get_type_data(type_name: str) -> dict[str, typing.Any]:
    return ALL_TYPES[type_name]
