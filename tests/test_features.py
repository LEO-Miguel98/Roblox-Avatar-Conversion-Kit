import unittest

from roblox_avatar_conversion_kit.features import analyze_features
from roblox_avatar_conversion_kit.obj import Face, ObjMesh
from roblox_avatar_conversion_kit.rig import Bone


class FeatureTests(unittest.TestCase):
    def test_detects_eye_rig_and_dynamic_hair_accessory(self):
        mesh = ObjMesh(
            vertices=[
                (-0.5, 1.5, -0.5), (0.5, 1.5, -0.5), (0.0, 2.5, -0.5),
                (-0.2, 2.2, -0.6), (0.2, 2.2, -0.6), (0.0, 2.8, -0.6),
            ],
            faces=[
                Face([(0, None, None), (1, None, None), (2, None, None)], "RigHead", None),
                Face([(3, None, None), (4, None, None), (5, None, None)], "HandleHair", None),
            ],
        )
        manifest = {
            "meshParts": [
                {"name": "Head", "cframe": [0.0, 2.0, 0.0], "size": [1.0, 1.0, 1.0]}
            ],
            "accessories": [
                {
                    "name": "Long Hair",
                    "handle": {
                        "fullName": "Avatar.Long Hair.Handle",
                        "cframe": [0.0, 2.4, -0.6],
                        "size": [0.6, 0.8, 0.2],
                    },
                }
            ],
            "joints": [
                {
                    "name": "AccessoryWeld",
                    "part0": "Avatar.Long Hair.Handle",
                    "part1": "Avatar.Head",
                }
            ],
        }
        features = analyze_features(
            manifest,
            mesh,
            (0.0, 0.0, 0.0),
            [Bone("head", None, (0.0, 2.0, 0.0))],
        )
        self.assertIsNotNone(features.eyes)
        self.assertFalse(features.native_expression_source)
        self.assertEqual(len(features.dynamics), 1)
        self.assertEqual(features.dynamics[0].group, "HandleHair")
        self.assertEqual(features.dynamics[0].parent_bone, "head")
        self.assertEqual(features.dynamics[0].physics_mode, "rigid")
        self.assertEqual(features.dynamics[0].segments, 0)
        self.assertIn("blink", features.expression_presets)

    def test_detects_wraplayer_as_layered_clothing(self):
        mesh = ObjMesh(
            vertices=[(-1, 0, 0), (1, 0, 0), (0, 1, 0)],
            faces=[Face([(0, None, None), (1, None, None), (2, None, None)], "Handle1", None)],
        )
        manifest = {
            "meshParts": [{"name": "Head", "cframe": [0, 2, 0], "size": [1, 1, 1]}],
            "accessories": [{
                "name": "Layered Jacket",
                "accessoryType": "Enum.AccessoryType.Jacket",
                "handle": {"fullName": "Avatar.Jacket.Handle", "cframe": [0, 0.3, 0], "size": [2, 1, 1]},
                "wrap": [{"className": "WrapLayer"}],
            }],
            "joints": [],
        }
        features = analyze_features(manifest, mesh, (0, 0, 0), [Bone("head", None, (0, 2, 0)), Bone("spine", None, (0, 0.5, 0))])
        self.assertEqual(len(features.layered_clothing), 1)
        self.assertEqual(features.layered_clothing[0].group, "Handle1")


if __name__ == "__main__":
    unittest.main()
