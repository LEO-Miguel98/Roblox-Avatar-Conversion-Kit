import unittest

from roblox_avatar_conversion_kit.face_surface_bind import (
    _closest_point_barycentric,
    _surface_bindings,
)
from roblox_avatar_conversion_kit.obj import Face, ObjMesh


class FaceSurfaceBindTests(unittest.TestCase):
    def test_closest_point_returns_barycentric_projection_inside_triangle(self):
        distance2, weights = _closest_point_barycentric(
            (0.25, 0.25, -0.40),
            (0.0, 0.0, -0.50),
            (1.0, 0.0, -0.50),
            (0.0, 1.0, -0.50),
        )
        self.assertAlmostEqual(distance2, 0.01, places=7)
        self.assertAlmostEqual(weights[0], 0.50, places=7)
        self.assertAlmostEqual(weights[1], 0.25, places=7)
        self.assertAlmostEqual(weights[2], 0.25, places=7)
        self.assertAlmostEqual(sum(weights), 1.0, places=7)

    def test_surface_binding_uses_restored_front_skin_not_unrelated_geometry(self):
        mesh = ObjMesh()
        mesh.vertices.extend([
            (0.0, 0.0, -0.50),
            (1.0, 0.0, -0.50),
            (0.0, 1.0, -0.50),
            # A rear skin triangle that is closer in XY but must be rejected by the front cut.
            (0.0, 0.0, 0.40),
            (1.0, 0.0, 0.40),
            (0.0, 1.0, 0.40),
            # Visible overlay artwork slightly in front of the real face shell.
            (0.25, 0.25, -0.56),
        ])
        mesh.faces.extend([
            Face([(0, None, None), (1, None, None), (2, None, None)], "RigHead", "FaceMtl__RACK_SKIN"),
            Face([(3, None, None), (4, None, None), (5, None, None)], "RigHead", "FaceMtl__RACK_SKIN"),
            Face([(6, None, None), (6, None, None), (6, None, None)], "RigHead", "FaceMtl"),
        ])

        bindings = _surface_bindings(
            mesh,
            "RigHead",
            {6},
            center=(0.5, 0.5, 0.0),
            size=(1.0, 1.0, 1.0),
        )
        self.assertIn(6, bindings)
        triangle, weights = bindings[6]
        self.assertEqual(triangle, (0, 1, 2))
        self.assertAlmostEqual(weights[0], 0.50, places=7)
        self.assertAlmostEqual(weights[1], 0.25, places=7)
        self.assertAlmostEqual(weights[2], 0.25, places=7)


if __name__ == "__main__":
    unittest.main()
