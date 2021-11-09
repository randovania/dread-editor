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
