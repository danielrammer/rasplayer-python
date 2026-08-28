import os
import unittest
from unittest import mock

from systemd_notify import WatchdogNotifier


class WatchdogNotifierTests(unittest.TestCase):
    def test_disabled_without_systemd_environment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            notifier = WatchdogNotifier()
        self.assertFalse(notifier.enabled)

    def test_interval_parsing(self):
        with mock.patch.dict(os.environ, {"NOTIFY_SOCKET": "@notify", "WATCHDOG_USEC": "10000000"}, clear=True):
            notifier = WatchdogNotifier()
        self.assertTrue(notifier.enabled)
        self.assertEqual(notifier.interval, 10.0)


if __name__ == "__main__":
    unittest.main()
