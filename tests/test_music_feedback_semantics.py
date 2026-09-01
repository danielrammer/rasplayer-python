import ast
from enum import IntEnum
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]


def load_rasplayer_function(name):
    """Load one owner-path function without executing RasPlayer startup."""
    tree = ast.parse((REPOSITORY / "RasPlayer.py").read_text(),
                     filename="RasPlayer.py")
    function = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name)
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 "RasPlayer.py", "exec"), namespace)
    return namespace, namespace[name]


class _PlayerMode(IntEnum):
    MUSIC = 0
    ONLINE = 3


class _Player:
    def __init__(self):
        self.navigation = []
        self.pause_calls = 0
        self.selections = []

    def navigate(self, offset):
        self.navigation.append(offset)
        return True

    def playPausePlayer(self):
        self.pause_calls += 1
        return True

    def buttonDown(self, button):
        self.selections.append(button)
        return True


class _Feedback:
    def __init__(self):
        self.calls = []

    def play(self, name, **metadata):
        self.calls.append((name, metadata))
        return True


class MusicFeedbackSemanticsTests(unittest.TestCase):
    def make_owner(self):
        namespace, process = load_rasplayer_function("_process_command")
        player = _Player()
        feedback = _Feedback()
        namespace.update({
            "shutting_down": False,
            "soundPlayer": player,
            "feedback": feedback,
            "PlayerMode": _PlayerMode,
            "playerMode": _PlayerMode.MUSIC,
            "mode_state": "ACTIVE",
            "mode_generation": 9,
        })
        return namespace, process, player, feedback

    def test_automatic_next_advances_without_feedback(self):
        _namespace, process, player, feedback = self.make_owner()

        process("automatic_next", 1)

        self.assertEqual(player.navigation, [1])
        self.assertEqual(feedback.calls, [])

    def test_physical_previous_and_next_each_acknowledge_once(self):
        _namespace, process, player, feedback = self.make_owner()

        process("navigation_delta", -1)
        process("navigation_delta", 1)

        self.assertEqual(player.navigation, [-1, 1])
        self.assertEqual(
            feedback.calls,
            [("generic", {"source": "navigation", "category": "navigation"}),
             ("generic", {"source": "navigation", "category": "navigation"})])

    def test_physical_playlist_selection_acknowledges_once(self):
        _namespace, process, player, feedback = self.make_owner()

        process("selection", {
            "button": 3,
            "generation": 9,
            "mode": _PlayerMode.MUSIC,
        })

        self.assertEqual(player.selections, [3])
        self.assertEqual(
            feedback.calls,
            [("generic", {"source": "selection", "category": "selection"})])

    def test_physical_play_pause_acknowledges_once(self):
        _namespace, process, player, feedback = self.make_owner()

        process("play_pause", None)

        self.assertEqual(player.pause_calls, 1)
        self.assertEqual(feedback.calls, [("generic", {})])

    def test_dispatch_keeps_automatic_next_distinct_from_user_navigation(self):
        namespace, dispatch = load_rasplayer_function("dispatch_player_input")
        commands = []
        namespace["enqueue_command"] = (
            lambda command, value=None: commands.append((command, value)))

        dispatch("automatic_next")
        dispatch("next")
        dispatch("previous")

        self.assertEqual(
            commands,
            [("automatic_next", 1),
             ("navigation_delta", 1),
             ("navigation_delta", -1)])


if __name__ == "__main__":
    unittest.main()
