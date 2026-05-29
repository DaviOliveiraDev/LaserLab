import os
import math
import sys
from pathlib import Path

# Add parent directory to path so backend imports resolve
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.parser.oma_parser import OMAParser
from backend.geometry.geo_engine import OphthalmicGeoEngine
from backend.laser.laser_integration import LaserPathGenerator

def run_diagnostic():
    print("=" * 60)
    print("   LENS LASER ENGRAVING AUTO-SYSTEM: DIAGNOSTIC RUNNER")
    print("=" * 60)
    
    # 1. Simulate OMA file contents representing a standard Freeform Progressive Lens
    print("\n[Step 1] Constructing mock progressive lens OMA file...")
    
    # Generate custom 360 trace points (oval lens)
    shape_lines = []
    for i in range(360):
        rad = math.radians(i)
        # Base radius 33mm, varying by 2mm for custom shape
        r_mm = 33.0 + 2.0 * math.cos(rad * 2.0)
        shape_lines.append(str(int(r_mm * 100))) # VCA units: 0.01 mm
        
    trcfmt_str = f"1;360;1.0;1.0;R;{';'.join(shape_lines)}"
    
    oma_content = f"""JOB=V-98765
EYE=R
LNAM=MVP Freeform SV 1.6
LDG=72.0
AXIS=45
ADD=2.50
PRISM=1.00
PBASE=180
TRCFMT={trcfmt_str}
"""
    print("-> Successfully created mock OMA file string (Job V-98765, Axis 45, Add +2.50).")
    
    # 2. Parse using OMAParser
    print("\n[Step 2] Triggering OMAParser...")
    parsed_data = OMAParser.parse_file(oma_content)
    
    print(f"-> Parsed Job ID: {parsed_data.get('JOB')}")
    print(f"-> Parsed Eye: {parsed_data.get('EYE')}")
    print(f"-> Parsed Axis: {parsed_data.get('AXIS')}°")
    print(f"-> Parsed Addition: +{parsed_data.get('ADD')}")
    print(f"-> Trace coordinates extracted: {len(parsed_data.get('shape_coordinates', []))} points.")
    
    if len(parsed_data.get('shape_coordinates', [])) != 360:
        print("x ERROR: TRCFMT radius point parsing failed.")
        return False
        
    # 3. Calculate geometry in Geo Engine
    print("\n[Step 3] Executing OphthalmicGeoEngine (with base curve 6.00D correction & custom offset calibration)...")
    calibration_factors = {
        "offset_x": 1.5,
        "offset_y": -0.5,
        "scale_x": 1.0,
        "scale_y": 1.0,
        "rotation": 0.5  # Skew rotation by 0.5 deg
    }
    
    geo_results = OphthalmicGeoEngine.calculate_geometry(
        shape_coords=parsed_data["shape_coordinates"],
        eye=parsed_data["EYE"],
        axis=parsed_data["AXIS"],
        addition=parsed_data["ADD"],
        base_curve=6.00,
        index=1.60,
        safety_margin=3.0,
        calibration=calibration_factors
    )
    
    # Add Job ID to metadata
    geo_results["markings"]["job_id"] = parsed_data.get("JOB")
    
    print("-> Bounding Box calculated:")
    print(f"   - Width: {geo_results['bbox']['width']:.2f} mm")
    print(f"   - Height: {geo_results['bbox']['height']:.2f} mm")
    print("-> Physical mark coordinates:")
    print(f"   - Nasal: X={geo_results['markings']['physical']['nasal']['x']:.3f}, Y={geo_results['markings']['physical']['nasal']['y']:.3f}")
    print(f"   - Temporal: X={geo_results['markings']['physical']['temporal']['x']:.3f}, Y={geo_results['markings']['physical']['temporal']['y']:.3f}")
    print("-> Curved pre-compensated coords:")
    print(f"   - Nasal: X={geo_results['markings']['curved_corrected']['nasal']['x']:.3f}, Y={geo_results['markings']['curved_corrected']['nasal']['y']:.3f}")
    print("-> Calibrated laser coords:")
    print(f"   - Nasal: X={geo_results['markings']['calibrated_laser']['nasal']['x']:.3f}, Y={geo_results['markings']['calibrated_laser']['nasal']['y']:.3f}")
    
    # 4. Generate laser vectors
    print("\n[Step 4] Launching LaserPathGenerator (generating G-code, SVG, and LBRN2)...")
    svg_out = LaserPathGenerator.generate_svg(geo_results)
    gcode_out = LaserPathGenerator.generate_gcode(geo_results)
    lbrn2_out = LaserPathGenerator.generate_lbrn2(geo_results)
    
    print(f"-> Generated SVG Preview length: {len(svg_out)} characters.")
    print(f"-> Generated G-Code file length: {len(gcode_out)} characters.")
    print(f"-> Generated LightBurn Native XML length: {len(lbrn2_out)} characters.")
    
    # Check simple regex/string presence
    if "svg" not in svg_out.lower() or "g21" not in gcode_out.lower() or "lightburnproject" not in lbrn2_out.lower():
        print("x ERROR: Output file templates are corrupted.")
        return False
        
    print("\n" + "=" * 60)
    print("   DIAGNOSTIC STATUS: ALL BACKEND MODULES FULLY OPERATIONAL!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = run_diagnostic()
    sys.exit(0 if success else 1)
