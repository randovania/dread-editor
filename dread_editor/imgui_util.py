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
