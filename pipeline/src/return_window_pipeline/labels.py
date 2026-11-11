from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from .errors import IntegrityError
from .models import safe_name

NS = {"p": "http://pds.nasa.gov/pds4/pds/v1", "c": "http://pds.nasa.gov/pds4/cart/v1", "g": "http://pds.nasa.gov/pds4/geom/v1"}


def read_pds4(path: Path) -> dict:
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper():
        raise IntegrityError("PDS4 labels with a DTD are not supported")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise IntegrityError(f"Invalid PDS4 XML: {error}") from error

    def get(query: str, required: bool = True):
        element = root.find(query, NS)
        if element is None or element.text is None or not element.text.strip():
            if required:
                raise IntegrityError(f"PDS4 label is missing {query}")
            return None
        return element.text.strip()

    if root.tag != f"{{{NS['p']}}}Product_Observational":
        raise IntegrityError("Expected a PDS4 observational product")
    images = root.findall("p:File_Area_Observational/p:Array_2D_Image", NS)
    if len(images) != 1 or len(root.findall("p:File_Area_Observational", NS)) != 1:
        raise IntegrityError("This adapter requires one two-dimensional PDS4 image")
    image = images[0]
    axis_arrays = image.findall("p:Axis_Array", NS)
    axes = {a.findtext("p:axis_name", namespaces=NS): int(a.findtext("p:elements", namespaces=NS)) for a in axis_arrays}
    if len(axis_arrays) != 2 or set(axes) != {"Line", "Sample"} or min(axes.values()) <= 0:
        raise IntegrityError("Unsupported PDS4 image axes")
    radii = []
    for axis in "abc":
        element = root.find(f".//c:{axis}_axis_radius", NS)
        if element is None or element.get("unit") not in {"km", "m"}:
            raise IntegrityError("PDS4 reference radii require explicit m or km units")
        radii.append(float(element.text) * (1000 if element.get("unit") == "km" else 1))
    def quantity(name):
        element = root.find(f".//c:{name}", NS)
        return (float(element.text), element.get("unit")) if element is not None else None

    bounds = ("west", "east", "south", "north")
    frame_base = ".//g:Orbiter_Identification"
    return {
        "logical_identifier": get("p:Identification_Area/p:logical_identifier"),
        "label_version": get("p:Identification_Area/p:version_id"),
        "title": get("p:Identification_Area/p:title"),
        "target": get("p:Observation_Area/p:Target_Identification/p:name"),
        "data_file": safe_name(get("p:File_Area_Observational/p:File/p:file_name"), "PDS4 data filename"),
        "shape": [axes["Line"], axes["Sample"]],
        "data_type": image.findtext("p:Element_Array/p:data_type", namespaces=NS),
        "value_unit": image.findtext("p:Element_Array/p:unit", namespaces=NS),
        "offset_bytes": int(image.findtext("p:offset", namespaces=NS)),
        "radii_m": radii,
        "latitude_type": get(".//c:latitude_type").lower(),
        "longitude_direction": get(".//c:longitude_direction"),
        "description": image.findtext("p:description", namespaces=NS),
        "planetary_bounds": {name: quantity(f"{name}_bounding_coordinate")[0] for name in bounds},
        "bounds_units": [quantity(f"{name}_bounding_coordinate")[1] for name in bounds],
        "frame": get(frame_base + "/g:Coordinate_System_Identification/g:Reference_Frame_Identification/g:name", False),
        "frame_origin": get(frame_base + "/g:Coordinate_System_Identification/g:Coordinate_System_Origin_Identification/g:name", False),
        "central_body": get(frame_base + "/g:Central_Body_Identification/g:name", False),
        "frame_latitude_type": get(frame_base + "/g:Coordinate_System_Identification/g:coordinate_system_type", False),
        "map_projection": get(".//c:map_projection_name", False),
        "grid": {key: quantity(key) for key in (
            "standard_parallel_1", "longitude_of_central_meridian", "pixel_resolution_x", "pixel_resolution_y",
            "pixel_scale_x", "pixel_scale_y", "upperleft_corner_x", "upperleft_corner_y")},
        "axes": int(image.findtext("p:axes", default="2", namespaces=NS)),
        "axis_order": image.findtext("p:axis_index_order", namespaces=NS),
        "axis_sequence": {a.findtext("p:axis_name", namespaces=NS): int(a.findtext("p:sequence_number", default="0", namespaces=NS)) for a in axis_arrays},
        "offset_unit": image.find("p:offset", NS).get("unit"),
        "scale": float(image.findtext("p:Element_Array/p:scaling_factor", default="1", namespaces=NS)),
        "value_offset": float(image.findtext("p:Element_Array/p:value_offset", default="0", namespaces=NS)),
        "special_constants": [element.tag.rsplit("}", 1)[-1] for element in image.findall("p:Special_Constants/*", NS)],
        "file_comment": get("p:File_Area_Observational/p:File/p:comment", False),
    }
