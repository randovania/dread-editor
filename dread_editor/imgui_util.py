import contextlib

import imgui


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
