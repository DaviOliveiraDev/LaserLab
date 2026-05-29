import math
from typing import Dict, Any, List, Tuple
import numpy as np
from shapely.geometry import Polygon, Point
from backend.config import (
    DEFAULT_MARK_DISTANCE_MM,
    DEFAULT_SAFETY_MARGIN_MM,
    DEFAULT_BASE_CURVE,
    DEFAULT_REFRACTIVE_INDEX,
    DEFAULT_CALIBRATION_X,
    DEFAULT_CALIBRATION_Y,
    DEFAULT_CALIBRATION_ROT,
    DEFAULT_CALIBRATION_SCALE_X,
    DEFAULT_CALIBRATION_SCALE_Y
)

class OphthalmicGeoEngine:
    """
    Geometric Engine responsible for coordinate calculation, axis rotation,
    safety margins verification, and curvature distortion compensation on lenses.
    """
    
    @staticmethod
    def calculate_geometry(
        shape_coords: List[Tuple[float, float]],
        eye: str,
        axis: float = 0.0,
        addition: float = None,
        base_curve: float = DEFAULT_BASE_CURVE,
        index: float = DEFAULT_REFRACTIVE_INDEX,
        safety_margin: float = DEFAULT_SAFETY_MARGIN_MM,
        calibration: Dict[str, float] = None,
        # Template Specific Parameters
        template_offset_x: float = 0.0,
        template_offset_y: float = 0.0,
        template_rotation: float = 0.0,
        fitting_cross_dist: float = 4.0,
        reference_point: str = "PRP"
    ) -> Dict[str, Any]:
        """
        Processes lens coordinates, computes technical markings, and applies corrections.
        Integrates lens design templates, reference points, and fitting cross translations.
        """
        # If no trace shape coords, construct a default round shape (e.g. 70mm diameter lens)
        if not shape_coords:
            shape_coords = OphthalmicGeoEngine._generate_default_round_shape(70.0)
            
        # Create Shapely Polygon
        lens_polygon = Polygon(shape_coords)
        
        # Calculate properties
        centroid = lens_polygon.centroid
        min_x, min_y, max_x, max_y = lens_polygon.bounds
        width = max_x - min_x
        height = max_y - min_y
        
        # Bounding box coordinates
        bbox = {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
            "width": width,
            "height": height
        }
        
        # Define Safety zone by buffering inwards
        safety_polygon = lens_polygon.buffer(-safety_margin)
        
        # Determine Reference Point Origin (x_ref, y_ref) in unrotated physical coordinates
        ref_x = 0.0
        ref_y = 0.0
        if reference_point == "GEOMETRIC_CENTER" or reference_point == "GC":
            ref_x = (min_x + max_x) / 2.0
            ref_y = (min_y + max_y) / 2.0
        elif reference_point == "DRP":
            # Distance Reference Point typically 6mm above alignment center
            ref_x = 0.0
            ref_y = 6.0
        elif reference_point == "MRP":
            ref_x = 0.0
            ref_y = 0.0
        # "PRP" (Prism Reference Point) remains at (0.0, 0.0)
        
        # Fitting Cross is placed fitting_cross_dist vertically above the chosen reference point
        fc_x = ref_x
        fc_y = ref_y + fitting_cross_dist
        
        # Standard markings spacing (usually 34mm apart)
        half_dist = DEFAULT_MARK_DISTANCE_MM / 2.0  # 17.0 mm
        
        # Eye orientation:
        # OD (Right Eye): Nasal is negative X (towards nose/left), Temporal is positive X (towards ear/right)
        # OS (Left Eye): Nasal is positive X (towards nose/right), Temporal is negative X (towards ear/left)
        is_left_eye = str(eye).upper() in ["L", "OS", "LEFT"]
        
        nasal_x = half_dist if is_left_eye else -half_dist
        temporal_x = -half_dist if is_left_eye else half_dist
        
        # Base physical markings relative to the Reference Point + template offsets
        # Apply offset_x and offset_y to shift the markings coordinates
        n_x = ref_x + nasal_x + template_offset_x
        n_y = ref_y + template_offset_y
        
        t_x = ref_x + temporal_x + template_offset_x
        t_y = ref_y + template_offset_y
        
        # Text labels positioned 3.0mm below the markings
        brand_text_pos = (t_x, t_y - 3.0)
        addition_text = f"{int(addition * 100):02d}" if addition else "20"
        addition_text_pos = (n_x, n_y - 3.0)
        
        # Rotate coordinates about blocking center (0,0) by cylinder axis + template_rotation
        rot_angle = math.radians(axis + template_rotation)
        
        # Helper to rotate coordinates about (0,0)
        def rotate_point(x: float, y: float, angle_rad: float) -> Tuple[float, float]:
            rx = x * math.cos(angle_rad) - y * math.sin(angle_rad)
            ry = x * math.sin(angle_rad) + y * math.cos(angle_rad)
            return rx, ry
            
        r_nasal_x, r_nasal_y = rotate_point(n_x, n_y, rot_angle)
        r_temporal_x, r_temporal_y = rotate_point(t_x, t_y, rot_angle)
        r_fc_x, r_fc_y = rotate_point(fc_x, fc_y, rot_angle)
        r_ref_x, r_ref_y = rotate_point(ref_x, ref_y, rot_angle)
        
        r_brand_x, r_brand_y = rotate_point(brand_text_pos[0], brand_text_pos[1], rot_angle)
        r_addition_x, r_addition_y = rotate_point(addition_text_pos[0], addition_text_pos[1], rot_angle)
        
        # Check Safety zone bounds using Shapely
        nasal_point = Point(r_nasal_x, r_nasal_y)
        temporal_point = Point(r_temporal_x, r_temporal_y)
        
        nasal_in_bounds = safety_polygon.contains(nasal_point)
        temporal_in_bounds = safety_polygon.contains(temporal_point)
        
        # Base Curve Correction (Sagitta Mathematical Compensation)
        try:
            r_curvature = (1.530 - 1.0) / base_curve * 1000.0  # e.g., 530 / 6 = 88.33 mm
        except ZeroDivisionError:
            r_curvature = 999999.0  # Flat lens
            
        def apply_spherical_correction(x: float, y: float) -> Tuple[float, float]:
            r_plane = math.sqrt(x**2 + y**2)
            if r_plane == 0:
                return 0.0, 0.0
            if r_plane >= r_curvature:
                return x, y
            scale = (r_curvature * math.sin(r_plane / r_curvature)) / r_plane
            return x * scale, y * scale

        # Apply base curve compensation
        c_nasal_x, c_nasal_y = apply_spherical_correction(r_nasal_x, r_nasal_y)
        c_temporal_x, c_temporal_y = apply_spherical_correction(r_temporal_x, r_temporal_y)
        c_fc_x, c_fc_y = apply_spherical_correction(r_fc_x, r_fc_y)
        c_ref_x, c_ref_y = apply_spherical_correction(r_ref_x, r_ref_y)
        c_brand_x, c_brand_y = apply_spherical_correction(r_brand_x, r_brand_y)
        c_addition_x, c_addition_y = apply_spherical_correction(r_addition_x, r_addition_y)
        
        # Apply Machine Calibration offsets if provided
        cal_x = calibration.get("offset_x", DEFAULT_CALIBRATION_X) if calibration else DEFAULT_CALIBRATION_X
        cal_y = calibration.get("offset_y", DEFAULT_CALIBRATION_Y) if calibration else DEFAULT_CALIBRATION_Y
        cal_rot = calibration.get("rotation", DEFAULT_CALIBRATION_ROT) if calibration else DEFAULT_CALIBRATION_ROT
        cal_scale_x = calibration.get("scale_x", DEFAULT_CALIBRATION_SCALE_X) if calibration else DEFAULT_CALIBRATION_SCALE_X
        cal_scale_y = calibration.get("scale_y", DEFAULT_CALIBRATION_SCALE_Y) if calibration else DEFAULT_CALIBRATION_SCALE_Y
        
        cal_rot_rad = math.radians(cal_rot)
        
        def apply_calibration(x: float, y: float) -> Tuple[float, float]:
            xs = x * cal_scale_x
            ys = y * cal_scale_y
            xr = xs * math.cos(cal_rot_rad) - ys * math.sin(cal_rot_rad)
            yr = xs * math.sin(cal_rot_rad) + ys * math.cos(cal_rot_rad)
            return xr + cal_x, yr + cal_y

        # Compute calibrated laser positions
        cal_nasal_x, cal_nasal_y = apply_calibration(c_nasal_x, c_nasal_y)
        cal_temporal_x, cal_temporal_y = apply_calibration(c_temporal_x, c_temporal_y)
        cal_fc_x, cal_fc_y = apply_calibration(c_fc_x, c_fc_y)
        cal_ref_x, cal_ref_y = apply_calibration(c_ref_x, c_ref_y)
        cal_brand_x, cal_brand_y = apply_calibration(c_brand_x, c_brand_y)
        cal_addition_x, cal_addition_y = apply_calibration(c_addition_x, c_addition_y)
        
        # Extract lens path coordinates for visual preview render (uncalibrated physical units)
        lens_polygon_coords = list(lens_polygon.exterior.coords)
        safety_polygon_coords = list(safety_polygon.exterior.coords) if not safety_polygon.is_empty else []

        return {
            "bbox": bbox,
            "centroid": {"x": centroid.x, "y": centroid.y},
            "lens_outline": [{"x": p[0], "y": p[1]} for p in lens_polygon_coords],
            "safety_outline": [{"x": p[0], "y": p[1]} for p in safety_polygon_coords],
            
            "markings": {
                "eye": eye,
                "is_left_eye": is_left_eye,
                "axis": axis,
                "addition_text": addition_text,
                "reference_point_type": reference_point,
                "fitting_cross_dist": fitting_cross_dist,
                
                # Uncalibrated physical coordinates for screen display
                "physical": {
                    "nasal": {"x": r_nasal_x, "y": r_nasal_y, "in_bounds": bool(nasal_in_bounds)},
                    "temporal": {"x": r_temporal_x, "y": r_temporal_y, "in_bounds": bool(temporal_in_bounds)},
                    "fitting_cross": {"x": r_fc_x, "y": r_fc_y},
                    "reference_point": {"x": r_ref_x, "y": r_ref_y},
                    "brand_text": {"x": r_brand_x, "y": r_brand_y},
                    "addition_text": {"x": r_addition_x, "y": r_addition_y}
                },
                
                # Curved corrected coordinates
                "curved_corrected": {
                    "nasal": {"x": c_nasal_x, "y": c_nasal_y},
                    "temporal": {"x": c_temporal_x, "y": c_temporal_y},
                    "fitting_cross": {"x": c_fc_x, "y": c_fc_y},
                    "reference_point": {"x": c_ref_x, "y": c_ref_y},
                    "brand_text": {"x": c_brand_x, "y": c_brand_y},
                    "addition_text": {"x": c_addition_x, "y": c_addition_y}
                },
                
                # Fully calibrated coordinates for laser hardware
                "calibrated_laser": {
                    "nasal": {"x": cal_nasal_x, "y": cal_nasal_y},
                    "temporal": {"x": cal_temporal_x, "y": cal_temporal_y},
                    "fitting_cross": {"x": cal_fc_x, "y": cal_fc_y},
                    "reference_point": {"x": cal_ref_x, "y": cal_ref_y},
                    "brand_text": {"x": cal_brand_x, "y": cal_brand_y},
                    "addition_text": {"x": cal_addition_x, "y": cal_addition_y}
                }
            },
            
            "parameters": {
                "base_curve": base_curve,
                "r_curvature": r_curvature,
                "safety_margin": safety_margin,
                "template_offset_x": template_offset_x,
                "template_offset_y": template_offset_y,
                "template_rotation": template_rotation
            }
        }
        
    @staticmethod
    def _generate_default_round_shape(diameter_mm: float) -> List[Tuple[float, float]]:
        """Generates a regular circle for tracing boundary when OMA file does not have a TRCFMT tag."""
        radius = diameter_mm / 2.0
        coords = []
        for i in range(360):
            rad = math.radians(i)
            coords.append((radius * math.cos(rad), radius * math.sin(rad)))
        return coords
