import os
import math
import sys
from pathlib import Path

# Add parent directory to path so backend imports resolve
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.database import engine, SessionLocal, Base
from backend.models import Job, LensTemplate, TemplateHistory
from backend.monitor.folder_monitor import process_job_pipeline, log_system_event
from backend.geometry.geo_engine import OphthalmicGeoEngine

def run_template_diagnostic():
    print("=" * 60)
    print("   LENS LASER ENGRAVING AUTO-SYSTEM: TEMPLATE AUTO-MATCH TEST")
    print("=" * 60)
    
    # 1. Initialize DB and Session
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    try:
        # 2. Register or fetch the active template
        template_name = "Zeiss Progressivo HD"
        print(f"\n[Step 1] Ensuring active Lens Template exists: '{template_name}'...")
        
        template = db.query(LensTemplate).filter(LensTemplate.name == template_name).first()
        if not template:
            template = LensTemplate(
                name=template_name,
                manufacturer="Zeiss",
                lens_type="Progressive",
                offset_x=2.50,            # +2.50 mm nasal shift
                offset_y=-1.50,           # -1.50 mm vertical shift
                rotation=1.50,            # 1.5° skew rotation
                fitting_cross_dist=4.50,  # FC is 4.5mm above PRP
                reference_point="PRP",
                technical_notes="Test template for progressive freeform engraving verification.",
                is_active=1
            )
            db.add(template)
            db.commit()
            db.refresh(template)
            
            # Log initial creation in audit history
            history = TemplateHistory(
                template_id=template.id,
                template_name=template.name,
                action="CREATE",
                changed_fields=dict(
                    name=template.name,
                    manufacturer=template.manufacturer,
                    offset_x=template.offset_x,
                    offset_y=template.offset_y,
                    rotation=template.rotation,
                    fitting_cross_dist=template.fitting_cross_dist,
                    reference_point=template.reference_point
                )
            )
            db.add(history)
            db.commit()
            print(f"-> Successfully registered template '{template_name}' (ID: {template.id}).")
        else:
            # Update to match our test settings to be deterministic
            template.offset_x = 2.50
            template.offset_y = -1.50
            template.rotation = 1.50
            template.fitting_cross_dist = 4.50
            template.reference_point = "PRP"
            template.is_active = 1
            db.commit()
            db.refresh(template)
            print(f"-> Found existing template '{template_name}' (ID: {template.id}). Reset parameters for test.")

        # 3. Create a simulated OMA job matching this template
        print("\n[Step 2] Constructing OMA file containing matching LNAM tag...")
        
        # Build 360 trace points (standard round lens, diameter 70mm -> radius 35mm)
        shape_lines = []
        for i in range(360):
            rad = math.radians(i)
            r_mm = 35.0
            shape_lines.append(str(int(r_mm * 100)))  # 0.01 mm units
            
        trcfmt_str = f"1;360;1.0;1.0;R;{';'.join(shape_lines)}"
        
        oma_content = f"""JOB=ZEISS-T-77
EYE=R
LNAM=Zeiss Progressivo HD Gold 1.6
LDG=70.0
AXIS=0
ADD=2.00
PRISM=0.0
PBASE=0.0
TRCFMT={trcfmt_str}
"""
        
        # Setup directories
        base_dir = Path(__file__).resolve().parent.parent
        output_dir = base_dir / "output_dir"
        output_dir.mkdir(exist_ok=True)
        
        test_filename = "zeiss_test_job.oma"
        test_filepath = base_dir / test_filename
        
        with open(test_filepath, "w", encoding="utf-8") as f:
            f.write(oma_content)
            
        print(f"-> Created test OMA file: {test_filepath}")
        
        # Capture template values before closing the session to prevent DetachedInstanceError
        expected_template_id = template.id
        expected_offset_x = template.offset_x
        expected_offset_y = template.offset_y
        expected_rotation = template.rotation
        expected_fc_dist = template.fitting_cross_dist
        expected_ref_point = template.reference_point
        expected_name = template.name

        # Delete any pre-existing job in DB to ensure fresh pipeline execution
        db.query(Job).filter(Job.filename == test_filename).delete()
        db.commit()
        db.close()
        
        # Open a fresh session to run the pipeline cleanly
        db = SessionLocal()
        
        # 4. Trigger pipeline
        print("\n[Step 3] Executing Folder Monitor Pipeline...")
        job = process_job_pipeline(db, str(test_filepath), test_filename)
        
        if not job:
            print("x ERROR: Pipeline failed to return processed job.")
            return False
            
        # Re-fetch job to get latest state
        db.refresh(job)
        
        print(f"-> Processed Job status: {job.status}")
        print(f"-> Matched Template ID: {job.template_id}")
        
        # 5. Core Assertions
        print("\n[Step 4] Validating Template Auto-Matching and Calculations...")
        
        # Assertion A: Verify template auto-detection worked via LNAM tag matching
        if job.template_id != expected_template_id:
            print(f"x ERROR: Template ID mismatch. Expected {expected_template_id}, got {job.template_id}")
            return False
        print(f"[OK] Match Check: OMA LNAM '{job.lens_name}' successfully matched Template '{expected_name}'.")
        
        # Assertion B: Verify geometric results are populated
        geo = job.geometry_json
        if not geo:
            print("x ERROR: Geometric JSON results are missing.")
            return False
            
        params = geo["parameters"]
        print(f"-> Extracted Applied Parameters from Geometry Engine:")
        print(f"   - offset_x: {params['template_offset_x']} mm (Expected: {expected_offset_x})")
        print(f"   - offset_y: {params['template_offset_y']} mm (Expected: {expected_offset_y})")
        print(f"   - rotation: {params['template_rotation']}° (Expected: {expected_rotation})")
        
        if params['template_offset_x'] != expected_offset_x or params['template_offset_y'] != expected_offset_y:
            print("x ERROR: Geometry parameters did not match template definitions.")
            return False
        print("[OK] Geometry Check: Template parameters correctly loaded into OphthalmicGeoEngine.")
        
        # Assertion C: Coordinate Offsets Shift Math
        # For an AXIS = 0, standard nasal position is -17.0mm (Right eye), temporal is +17.0mm.
        # Reference point PRP is at (0.0, 0.0).
        # Unrotated, nasal center shifts to: -17.0 + offset_x = -17.0 + 2.50 = -14.50 mm.
        # Vertical shifts to: 0.0 + offset_y = -1.50 mm.
        # Fitting cross is at: ref_x = 0.0, ref_y + fitting_cross_dist = 4.50 mm.
        # These are then rotated by axis (0) + template_rotation (1.5°).
        # Let's verify that the computed coordinates reflect these equations.
        m = geo["markings"]["physical"]
        
        # Unrotated reference point
        ref_x = 0.0
        ref_y = 0.0
        # Expected nasal position before 1.5° rotation:
        base_n_x = ref_x - 17.0 + expected_offset_x  # -14.5 mm
        base_n_y = ref_y + expected_offset_y         # -1.5 mm
        
        # Apply 1.5° rotation to (base_n_x, base_n_y)
        rot_rad = math.radians(expected_rotation)
        expected_n_x = base_n_x * math.cos(rot_rad) - base_n_y * math.sin(rot_rad)
        expected_n_y = base_n_x * math.sin(rot_rad) + base_n_y * math.cos(rot_rad)
        
        actual_n_x = m["nasal"]["x"]
        actual_n_y = m["nasal"]["y"]
        
        print(f"-> Marking Coordinate Calculations:")
        print(f"   - Expected Nasal: X={expected_n_x:.4f}, Y={expected_n_y:.4f}")
        print(f"   - Actual Nasal:   X={actual_n_x:.4f}, Y={actual_n_y:.4f}")
        
        if not math.isclose(expected_n_x, actual_n_x, abs_tol=1e-3) or not math.isclose(expected_n_y, actual_n_y, abs_tol=1e-3):
            print("x ERROR: Nasal marking position calculation does not match template geometry math.")
            return False
        print("[OK] Coordinate Check: Technical markings are precisely aligned using template shifts and rotational skews.")
        
        # Verify physical output files
        print("\n[Step 5] Checking physical output files on disk...")
        svg_exists = os.path.exists(job.svg_path)
        gcode_exists = os.path.exists(job.gcode_path)
        lbrn2_exists = os.path.exists(job.lbrn2_path)
        
        print(f"   - SVG Preview:   {job.svg_path} (Exists: {svg_exists})")
        print(f"   - GRBL G-Code:   {job.gcode_path} (Exists: {gcode_exists})")
        print(f"   - LightBurn Project: {job.lbrn2_path} (Exists: {lbrn2_exists})")
        
        if not (svg_exists and gcode_exists and lbrn2_exists):
            print("x ERROR: Output files are missing on disk.")
            return False
        print("[OK] Output Check: Industrial vector files successfully generated.")
        
        # Clean up files after test
        os.remove(test_filepath)
        print(f"\n-> Cleaned up test OMA file: {test_filepath}")
        
        print("\n" + "=" * 60)
        print("   TEMPLATE SYSTEM STATUS: 100% CORRECT & AUTOMATED MATCHING PASS!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"x ERROR: Test crashed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = run_template_diagnostic()
    sys.exit(0 if success else 1)
