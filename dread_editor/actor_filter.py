import construct
import imgui


class ActorFilter:
    name_filter: str

    def __init__(self):
        self.name_filter = ""

    def draw(self):
        self.name_filter = imgui.input_text("Filter", self.name_filter, 500)[1]

    def passes(self, actor: construct.Container) -> bool:
        if not self.name_filter:
            return True

        actor_name = actor.sName

        for criteria in self.name_filter.split(","):
            criteria = criteria.strip()
            if criteria[0] == "-":
                if criteria[1:] in actor_name:
                    return False
            else:
                if criteria not in actor_name:
                    return False

        return True
