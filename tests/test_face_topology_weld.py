import unittest

from roblox_avatar_conversion_kit.face_topology_weld import (
    _eye_loop_field,
    _eye_pair_targets,
    _mouth_base_field,
)


class _Mesh:
    def __init__(self, vertices):
        self.vertices = vertices


class FaceTopologyWeldTests(unittest.TestCase):
    def test_blink_closes_real_socket_loop_to_shared_curve(self):
        vertices = [
            (-0.30, 0.10, 0.0), (-0.10, 0.16, 0.0), (0.10, 0.15, 0.0), (0.30, 0.09, 0.0),
            (-0.30, -0.08, 0.0), (-0.10, -0.12, 0.0), (0.10, -0.11, 0.0), (0.30, -0.07, 0.0),
        ]
        mesh = _Mesh(vertices)
        loop = frozenset(range(len(vertices)))
        targets = _eye_pair_targets(mesh, loop)
        field = _eye_loop_field(mesh, loop, "blink")
        self.assertEqual(set(field), set(loop))
        for index in loop:
            self.assertAlmostEqual(
                mesh.vertices[index][1] + field[index][1], targets[index], places=7
            )

    def test_smile_moves_skin_mouth_corners_outward_and_up(self):
        vertices = [
            (-0.20, 0.00, 0.0), (-0.10, 0.00, 0.0),
            (0.10, 0.00, 0.0), (0.20, 0.00, 0.0),
            (-0.18, 0.02, 0.0), (-0.12, 0.01, 0.0), (-0.06, 0.00, 0.0), (-0.02, 0.00, 0.0),
            (0.02, 0.00, 0.0), (0.06, 0.00, 0.0), (0.12, 0.01, 0.0), (0.18, 0.02, 0.0),
        ]
        mesh = _Mesh(vertices)
        anchors = frozenset(range(4))
        driver = frozenset(range(4, 12))
        field = _mouth_base_field(mesh, anchors, driver, "smile")
        left = min(field, key=lambda index: mesh.vertices[index][0])
        right = max(field, key=lambda index: mesh.vertices[index][0])
        self.assertLess(field[left][0], 0.0)
        self.assertGreater(field[right][0], 0.0)
        self.assertGreater(field[left][1], 0.0)
        self.assertGreater(field[right][1], 0.0)

    def test_mouth_open_uses_same_master_skin_field(self):
        vertices = [
            (-0.12, -0.03, 0.0), (0.12, -0.03, 0.0),
            (-0.12, 0.03, 0.0), (0.12, 0.03, 0.0),
            (-0.10, -0.02, 0.0), (-0.07, -0.01, 0.0), (-0.03, 0.00, 0.0), (-0.01, 0.00, 0.0),
            (0.01, 0.00, 0.0), (0.03, 0.00, 0.0), (0.07, 0.01, 0.0), (0.10, 0.02, 0.0),
        ]
        mesh = _Mesh(vertices)
        anchors = frozenset(range(4))
        driver = frozenset(range(4, 12))
        field = _mouth_base_field(mesh, anchors, driver, "open")
        lower = [index for index in anchors if mesh.vertices[index][1] < 0.0]
        upper = [index for index in anchors if mesh.vertices[index][1] > 0.0]
        self.assertTrue(all(field[index][1] < 0.0 for index in lower))
        self.assertTrue(all(field[index][1] > 0.0 for index in upper))


if __name__ == "__main__":
    unittest.main()
