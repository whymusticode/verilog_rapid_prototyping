"""Regression cases for stream measurements: payload metrics exclude metadata."""
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from vrp import Stream, load_params, load_reference, load_stream, measure
from evald import measurements


def stream(y, groups, primary='all', ready=None):
    y = np.asarray(y, dtype=float)
    return Stream(np.zeros(4), 1, y, 1, np.asarray(ready if ready is not None else np.zeros(len(y), int)),
                  (16, 0, True), (16, 0, True), {k: np.asarray(v, bool) for k, v in groups.items()}, primary)


class StreamMeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = (Path(__file__).parent / 'Projects/turbo-3gpp/main.py').resolve()
        params = load_params(path)
        cls.turbo = load_stream(load_reference(path, params), params, 20000, np.random.default_rng())

    def test_turbo_groups_partition_the_bit_stream(self):
        s = self.turbo
        self.assertEqual(s.primary, 'payload')
        self.assertEqual(sum(mask.sum() for mask in s.groups.values()), len(s.y))
        self.assertTrue(np.all((s.y == 0) | (s.y == 1)))
        self.assertTrue(np.all(np.diff(s.ready) >= 0))

    def test_zero_payload_cannot_hide_behind_metadata(self):
        s = self.turbo
        actual = s.y.copy()
        actual[s.groups['payload']] = 0
        measured = measure(s, actual, len(s.y))
        ones = s.y[s.groups['payload']].mean()
        self.assertEqual(measured['payload']['mismatches'], int(s.y[s.groups['payload']].sum()))
        self.assertAlmostEqual(measured['payload']['precision_bits'], -0.5 * np.log2(ones))
        for name in ('crc', 'length', 'modulation', 'symbols'):
            self.assertEqual(measured[name]['mismatches'], 0)

    def test_metadata_errors_are_measured_separately(self):
        s = stream([1, 0, 1, 1], {'payload': [0, 0, 1, 1], 'crc': [1, 1, 0, 0]}, 'payload')
        measured = measure(s, [0, 0, 1, 1], 4)
        self.assertEqual(measured['payload']['mismatches'], 0)
        self.assertEqual(measured['crc']['mismatches'], 1)

    def test_empty_group_has_no_precision(self):
        s = stream([1.0], {'payload': [False], 'crc': [True]}, 'payload')
        measured = measure(s, [1.0], 1)
        self.assertEqual(measured['payload']['samples'], 0)
        self.assertIsNone(measured['payload']['precision_bits'])

    def test_only_the_measured_prefix_counts(self):
        s = stream([1, 1, 1, 1], {'all': [1, 1, 1, 1]})
        self.assertEqual(measure(s, [1, 1, 0, 0], 2)['all']['mismatches'], 0)

    def test_framed_projects_become_streams(self):
        frames = [np.array([0., 1.]), np.array([1., 0.])]
        module = SimpleNamespace(target=lambda x: x * (1 + 1j), inputs=lambda rng, n: frames[:n])
        s = load_stream(module, {'N': 2, 'bits': 16}, 4, np.random.default_rng())
        self.assertEqual((s.frame, s.samples, s.in_lanes, s.out_lanes), (2, 4, 1, 2))
        self.assertEqual(list(s.ready), [2, 2, 2, 2, 4, 4, 4, 4])

    def test_generated_groups_must_partition_outputs(self):
        for groups in ({'x': [True, False]}, {'x': [True, True], 'y': [True, True]}):
            module = SimpleNamespace(generate=lambda n, g=groups: dict(x=np.zeros(2), y=np.ones(2),
                                                                      ready=[1, 2], groups=g))
            with self.assertRaisesRegex(ValueError, 'partition'):
                load_stream(module, {'input': {'bits': 8}, 'output': {'bits': 8}}, 2, None)

    def test_evaluation_log_retains_group_measurements(self):
        result = measurements('measurement group: payload\nbits of precision: 0.5\nRMS error: 0.707\n'
                              'throughput: 9.5 cycles/sample\n'
                              'output group payload: 2 mismatches / 4 samples; RMSE=0.707\n'
                              'output group crc: 1 mismatches / 1 samples; RMSE=1.0\n')
        self.assertEqual(result['measurement_group'], 'payload')
        self.assertEqual(result['cycles_per_sample'], 9.5)
        self.assertEqual(result['output_groups']['payload']['mismatches'], 2)
        self.assertEqual(result['output_groups']['crc']['samples'], 1)


if __name__ == '__main__':
    unittest.main()
