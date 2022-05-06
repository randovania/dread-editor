import contextlib
import typing

import imgui

T = typing.TypeVar("T")


@contextlib.contextmanager
def with_child(*args, **kwargs):
    result = imgui.begin_child(*args, **kwargs)
    yield result
    imgui.end_child()


@contextlib.contextmanager
def with_group():
    imgui.begin_group()
    yield
    imgui.end_group()


def colored_tree_node(text: str, color, flags=0):
    with imgui.colored(imgui.COLOR_TEXT, *color):
        return imgui.tree_node(text, flags)


def tree_node_with_column(text: str, flags=0):
    result = imgui.tree_node(text, flags)
    imgui.next_column()
    imgui.next_column()
    return result


def set_hovered_tooltip(tooltip: str):
    if imgui.is_item_hovered():
        imgui.set_tooltip(tooltip)


_input_text_persistence = {}


def persistent_input_text(label: str, path: str, initial_value: str = "", max_size: int = 500):
    if path not in _input_text_persistence:
        _input_text_persistence[path] = initial_value

    changed, result = imgui.input_text(f"{label}##{path}", _input_text_persistence[path], max_size)
    if changed:
        _input_text_persistence[path] = result
    return changed, result


def combo_str(label: str, current: str, items: list[str], height_in_items: int = -1) -> tuple[bool, str]:
    changed, selected = imgui.combo(label, items.index(current), items, height_in_items)
    selected = items[selected]
    return changed, selected


def combo_enum(label: str, current: T, enum_class: typing.Type[T], height_in_items: int = -1) -> tuple[bool, T]:
    items: list[T] = list(enum_class)
    changed, selected = imgui.combo(label, items.index(current), [x.name for x in items], height_in_items)
    selected = items[selected]
    return changed, selected


def combo_flagset(label: str, current: dict[T, bool], enum_class: typing.Type[T]) -> tuple[bool, T]:
    changed, selected = False, current

    if imgui.button(f"Select flags ##{label}"):
        imgui.open_popup(label)

    if imgui.begin_popup_modal(label)[0]:
        for i, item in enumerate(enum_class):
            item_changed, new_item = imgui.checkbox(f"{item.name} ##{label}.item_{i}", current[item.name])
            if item_changed:
                current[item.name] = new_item
            changed = changed or item_changed

        if imgui.button(f"Close ##{label}"):
            imgui.close_current_popup()

        imgui.end_popup()

    return changed, selected
