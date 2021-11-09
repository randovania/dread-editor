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
