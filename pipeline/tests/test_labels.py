from pathlib import Path
import tempfile
import unittest

from return_window_pipeline.errors import IntegrityError
from return_window_pipeline.ingestion import validate_label_files
from return_window_pipeline.labels import read_pds4

XML = '''<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1" xmlns:cart="http://pds.nasa.gov/pds4/cart/v1">
<Identification_Area><logical_identifier>urn:test:mars:terrain</logical_identifier><version_id>1.1</version_id><title>Test terrain</title></Identification_Area>
<Observation_Area><Target_Identification><name>Mars</name></Target_Identification>
<Discipline_Area><cart:Cartography><cart:Geodetic_Model><cart:a_axis_radius unit="km">3396</cart:a_axis_radius><cart:b_axis_radius unit="km">3396</cart:b_axis_radius><cart:c_axis_radius unit="km">3396</cart:c_axis_radius><cart:latitude_type>Planetocentric</cart:latitude_type><cart:longitude_direction>Positive East</cart:longitude_direction></cart:Geodetic_Model>
<cart:Bounding_Coordinates><cart:west_bounding_coordinate>0</cart:west_bounding_coordinate><cart:east_bounding_coordinate>360</cart:east_bounding_coordinate><cart:south_bounding_coordinate>-90</cart:south_bounding_coordinate><cart:north_bounding_coordinate>90</cart:north_bounding_coordinate></cart:Bounding_Coordinates></cart:Cartography></Discipline_Area></Observation_Area>
<File_Area_Observational><File><file_name>terrain.img</file_name></File><Array_2D_Image><offset>0</offset><Element_Array><data_type>SignedMSB2</data_type><unit>meter</unit></Element_Array><Axis_Array><axis_name>Line</axis_name><elements>2</elements></Axis_Array><Axis_Array><axis_name>Sample</axis_name><elements>2</elements></Axis_Array></Array_2D_Image></File_Area_Observational></Product_Observational>'''


class LabelTests(unittest.TestCase):
    def test_label_identity_units_and_dimensions(self):
        with tempfile.TemporaryDirectory(prefix="return-window-label-") as directory:
            path = Path(directory) / "terrain.xml"
            path.write_text(XML)
            label = read_pds4(path)
            self.assertEqual(label["radii_m"], [3396000, 3396000, 3396000])
            self.assertEqual(label["shape"], [2, 2])
            self.assertEqual(label["label_version"], "1.1")
            (Path(directory) / "terrain.img").write_bytes(b"\x00" * 8)
            validate_label_files(label, Path(directory), "urn:test:mars:terrain", "1.1")
            with self.assertRaises(IntegrityError):
                validate_label_files(label, Path(directory), "urn:test:mars:terrain", "1.0")
            (Path(directory) / "terrain.img").write_bytes(b"\x00" * 6)
            with self.assertRaises(IntegrityError):
                validate_label_files(label, Path(directory), "urn:test:mars:terrain", "1.1")

    def test_invalid_xml_and_unsupported_root_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="return-window-label-") as directory:
            path = Path(directory) / "invalid.xml"
            for content in ["not xml", "<anything/>", '<!DOCTYPE x [<!ENTITY y "z">]><x/>']:
                path.write_text(content)
                with self.assertRaises(IntegrityError):
                    read_pds4(path)
