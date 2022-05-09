from typing import Optional

import construct
import imgui

from dread_editor import imgui_util


class ActorFilter:
    name_filter: str = ""
    case_sensitive_name: bool = False
    expected_component: str = ""
    expected_actordef: str = ""

    _popup_label: str

    def __init__(self):
        self._popup_label = "Advanced actor filters"

    def draw(self, current_scale: float):
        if imgui.button(f"Filters ##{self._popup_label}"):
            imgui.open_popup(self._popup_label)

        imgui.set_next_window_size(550 * current_scale, 150 * current_scale)
        if imgui.begin_popup_modal(self._popup_label)[0]:
            self.case_sensitive_name = imgui.checkbox("Case sensitive", self.case_sensitive_name)[1]
            imgui.same_line()
            self.name_filter = imgui.input_text("Filter by name", self.name_filter, 500)[1]

            self.expected_component = imgui.input_text("Must have component", self.expected_component, 300)[1]

            self.expected_actordef = imgui.input_text("Match actordef", self.expected_actordef, 500)[1]

            if imgui.button(f"Close ##{self._popup_label}"):
                imgui.close_current_popup()

            imgui.end_popup()

    def passes(self, actor: construct.Container) -> bool:
        if self.name_filter:
            actor_name: str = actor.sName
            if self.case_sensitive_name:
                actor_name = actor_name.lower()

            for criteria in self.name_filter.split(","):
                criteria = criteria.strip()
                if self.case_sensitive_name:
                    criteria = criteria.lower()

                if criteria[0] == "-":
                    if criteria[1:] in actor_name:
                        return False
                else:
                    if criteria not in actor_name:
                        return False

        if self.expected_component:
            if not any(self.expected_component.lower() in component_name.lower()
                       for component_name in actor.pComponents):
                return False

        if self.expected_actordef:
            if self.expected_actordef not in actor.oActorDefLink:
                return False

        return True
