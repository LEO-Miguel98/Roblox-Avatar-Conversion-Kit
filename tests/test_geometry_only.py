import unittest

from roblox_avatar_conversion_kit.geometry_only import (
    infer_geometry_only_avatar,
    normalize_geometry_only_mesh,
)
from roblox_avatar_conversion_kit.obj import Face, ObjMesh


def add_box(mesh: ObjMesh, group: str, center, size):
    base = len(mesh.vertices)
    cx, cy, cz = center
    sx, sy, sz = (value * 0.5 for value in size)
    corners = [
        (cx - sx, cy - sy, cz - sz), (cx + sx, cy - sy, cz - sz),
        (cx + sx, cy + sy, cz - sz), (cx - sx, cy + sy, cz - sz),
        (cx - sx, cy - sy, cz + sz), (cx + sx, cy - sy, cz + sz),
        (cx + sx, cy + sy, cz + sz), (cx - sx, cy + sy, cz + sz),
    ]
    mesh.vertices.extend(corners)
    triangles = [
        (0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6),
        (0, 4, 5), (0, 5, 1), (3, 2, 6), (3, 6, 7),
        (0, 3, 7), (0, 7, 4), (1, 5, 6), (1, 6, 2),
    ]
    for tri in triangles:
        mesh.faces.append(Face([(base + i, None, None) for i in tri], group, None))


class GeometryOnlyTests(unittest.TestCase):
    def _mesh(self):
        mesh = ObjMesh()
        add_box(mesh, "Baseplate1", (0, -5, 0), (100, 1, 100))
        # Diane-style 11 visible Rig groups: head, two centered torso groups,
        # upper-arm pair, hand pair, upper-leg pair, foot pair.
        specs = {
            "Rig1": (-0.84, 1.59, -0.06, 0.40, 0.20, 0.48),
            "Rig2": (0.30, 1.02, -0.06, 0.38, 0.26, 0.52),
            "Rig3": (0.27, 1.35, -0.04, 0.46, 0.81, 0.59),
            "Rig4": (-0.30, 1.02, -0.05, 0.39, 0.26, 0.50),
            "Rig5": (-0.27, 1.35, -0.04, 0.45, 0.81, 0.59),
            "Rig6": (-0.35, 2.51, -0.04, 0.41, 0.60, 0.29),
            "Rig7": (0.00, 3.46, 0.00, 1.19, 1.14, 1.15),
            "Rig8": (0.84, 1.59, -0.06, 0.41, 0.20, 0.48),
            "Rig9": (0.35, 2.51, -0.03, 0.41, 0.60, 0.29),
            "Rig10": (0.00, 1.63, 0.01, 0.81, 0.70, 0.54),
            "Rig11": (0.00, 2.48, -0.09, 0.57, 1.16, 0.52),
        }
        for name, values in specs.items():
            add_box(mesh, name, values[:3], values[3:])
        add_box(mesh, "HandleHeart", (0, 4.50, 0.03), (0.56, 0.65, 0.07))
        add_box(mesh, "HandleTail", (0, 1.55, 1.60), (1.05, 2.15, 3.30))
        add_box(mesh, "HandleJacket", (0, 2.05, 0.05), (1.90, 1.35, 1.10))
        return mesh

    def test_normalizes_scene_and_infers_tail_heart_and_humanoid(self):
        mesh = self._mesh()
        normalize_geometry_only_mesh(mesh)
        self.assertNotIn("Baseplate1", mesh.group_vertex_indices())

        bones, mapping, features, warnings = infer_geometry_only_avatar(mesh)
        names = {bone.name for bone in bones}
        self.assertTrue({"hips", "spine", "chest", "neck", "head"}.issubset(names))
        self.assertTrue({"leftUpperArm", "leftLowerArm", "leftHand"}.issubset(names))
        self.assertTrue({"rightUpperLeg", "rightLowerLeg", "rightFoot"}.issubset(names))
        self.assertEqual(mapping["HandleHeart"], "head")
        self.assertEqual(mapping["HandleTail"], "hips")

        dynamics = {item.name: item for item in features.dynamics}
        self.assertEqual(dynamics["Shark tail"].segments, 4)
        self.assertEqual(dynamics["Heart hair / cowlick"].segments, 2)
        self.assertLess(dynamics["Heart hair / cowlick"].angular_limit, 0.10)
        self.assertGreater(dynamics["Heart hair / cowlick"].drag_force, 0.85)
        self.assertIsNotNone(features.eyes)
        self.assertTrue(any(item.profile == "upper_body" for item in features.layered_clothing))
        self.assertTrue(any("geometry-only" in warning.lower() for warning in warnings))


if __name__ == "__main__":
    unittest.main()
