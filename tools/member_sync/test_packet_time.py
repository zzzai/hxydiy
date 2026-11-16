"""Keep the exact freshness gate while allowing a short clock lead to elapse."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
import packet

class ObservationTimeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 16, tzinfo=timezone.utc)

    def test_small_clock_lead_waits_before_exact_gate(self):
        observed = self.now + timedelta(seconds=0.25)
        with patch.object(packet, "datetime") as clock, patch.object(packet, "time") as timer:
            clock.now.side_effect = [self.now, observed + timedelta(milliseconds=1)]
            packet.validate_observation_time(observed)
            timer.sleep.assert_called_once_with(0.25)

    def test_clock_still_ahead_stops_after_one_wait(self):
        observed = self.now + timedelta(seconds=1)
        with patch.object(packet, "datetime") as clock, patch.object(packet, "time") as timer:
            clock.now.return_value = self.now
            with self.assertRaisesRegex(AssertionError, "source_observation_stale"):
                packet.validate_observation_time(observed)
            timer.sleep.assert_called_once_with(1)

    def test_large_clock_lead_and_stale_sources_stop_without_wait(self):
        for delta in (6, -7201):
            with self.subTest(delta=delta), patch.object(packet, "datetime") as clock, patch.object(packet, "time") as timer:
                clock.now.return_value = self.now
                with self.assertRaisesRegex(AssertionError, "source_observation_stale"):
                    packet.validate_observation_time(self.now + timedelta(seconds=delta))
                timer.sleep.assert_not_called()

    def test_fresh_source_needs_no_wait(self):
        with patch.object(packet, "datetime") as clock, patch.object(packet, "time") as timer:
            clock.now.return_value = self.now
            packet.validate_observation_time(self.now - timedelta(seconds=1))
            timer.sleep.assert_not_called()

if __name__ == "__main__": unittest.main()
