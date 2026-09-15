import unittest

from roblox_avatar_conversion_kit.features import FeaturePlan, LayeredClothing
from roblox_avatar_conversion_kit.obj import Material
from roblox_avatar_conversion_kit.pmx import _geometry_only_textured_materials, _pmx_diffuse


class MaterialFidelityTests(unittest.TestCase):
    def test_geometry_only_textured_materials_use_neutral_diffuse(self):
        features = FeaturePlan(
            eyes=None,
            dynamics=(),
            layered_clothing=(
                LayeredClothing(
                    name="Inferred jacket",
                    group="Handle2",
                    accessory_type="GeometryOnly",
                    profile="upper_body",
                ),
            ),
        )
        material = Material(
            "Hair",
            kd=(0.373615, 0.368591, 0.383775),
            map_kd="Handle10_diff.png",
        )
        self.assertTrue(_geometry_only_textured_materials(features))
        self.assertEqual(
            _pmx_diffuse(material, neutralize_textured=True),
            (1.0, 1.0, 1.0),
        )

    def test_manifest_style_material_keeps_mtl_tint(self):
        features = FeaturePlan(eyes=None, dynamics=())
        material = Material(
            "Tinted",
            kd=(0.25, 0.5, 0.75),
            map_kd="texture.png",
        )
        self.assertFalse(_geometry_only_textured_materials(features))
        self.assertEqual(
            _pmx_diffuse(material, neutralize_textured=False),
            material.kd,
        )

    def test_untextured_material_keeps_color_even_in_geometry_only_mode(self):
        material = Material("Solid", kd=(0.2, 0.3, 0.4), map_kd=None)
        self.assertEqual(
            _pmx_diffuse(material, neutralize_textured=True),
            material.kd,
        )


if __name__ == "__main__":
    unittest.main()
