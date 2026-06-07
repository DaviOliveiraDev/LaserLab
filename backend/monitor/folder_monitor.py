import os
import time
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy.orm import Session
import logging

from backend.config import WATCH_DIR, OUTPUT_DIR

# Global registry for active processing to prevent concurrent pipeline collisions
processing_files = set()
processing_files_lock = threading.Lock()
from backend.database import SessionLocal, Base, engine
from backend.models import Job, Calibration, SystemLog, LensTemplate, OrderFlow, ProductionLog
from backend.parser.oma_parser import OMAParser
from backend.geometry.geo_engine import OphthalmicGeoEngine
from backend.laser.laser_integration import LaserPathGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_or_create_calibration(db: Session) -> Calibration:
    """Helper to ensure a baseline calibration record always exists."""
    cal = db.query(Calibration).first()
    if not cal:
        cal = Calibration(
            offset_x=0.0,
            offset_y=0.0,
            scale_x=1.0,
            scale_y=1.0,
            rotation=0.0
        )
        db.add(cal)
        db.commit()
        db.refresh(cal)
    return cal

def log_system_event(db: Session, level: str, message: str):
    """Helper to write diagnostic logging into the SQLite database."""
    log_entry = SystemLog(level=level, message=message)
    db.add(log_entry)
    db.commit()
    logger.info(f"[{level}] {message}")

def log_production_event(db: Session, job_id: str, event_type: str, message: str, lens_side: str = "NONE"):
    """Helper to write operational production events to database."""
    log_entry = ProductionLog(
        job_id=job_id,
        event_type=event_type,
        message=message,
        lens_side=lens_side
    )
    db.add(log_entry)
    db.commit()
    logger.info(f"[PRODUCTION_LOG] [{event_type}] Lens: {lens_side} - Job: {job_id} - {message}")

def process_job_pipeline(db: Session, filepath: str, filename: str, force_reprocess: bool = False) -> Job:
    """
    Core pipeline: parses the OMA, calculates lens geometry,
    applies calibration, generates output vectors, and commits to SQLite.
    """
    is_processing = False
    with processing_files_lock:
        if filename in processing_files:
            is_processing = True
        else:
            processing_files.add(filename)

    if is_processing:
        logger.info(f"File {filename} is already being processed by another thread. Waiting...")
        # Wait for the other thread to complete (up to 10 seconds)
        for _ in range(50):
            time.sleep(0.2)
            with processing_files_lock:
                if filename not in processing_files:
                    break
        db.expire_all()
        job = db.query(Job).filter(Job.filename == filename).first()
        if job:
            logger.info(f"File {filename} processing completed by other thread. Status: {job.status}")
            return job
        return None

    try:
        try:
            # Give a small delay to ensure file write locks are released
            time.sleep(0.15)
            # 1. Read OMA File
            if not os.path.exists(filepath):
                return None
                
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                oma_content = f.read()
                
            if not oma_content.strip():
                # File is empty (triggered prematurely), skip and wait for modification event
                return None
        except Exception as e:
            logger.error(f"Cannot read file {filepath}: {e}")
            return None

        # Deduplication check: if file already exists in database with identical content, skip
        job = db.query(Job).filter(Job.filename == filename).first()
        if not force_reprocess and job and job.oma_data == oma_content:
            if job.status in ["Parsing", "Calculating", "Ready", "Success", "Failed"] or job.status.startswith("Streaming"):
                logger.info(f"Skipping duplicate processing for {filename} (status: {job.status})")
                return job

        log_system_event(db, "INFO", f"Triggering processing for: {filename}")

        if not job:
            from sqlalchemy.exc import IntegrityError
            try:
                job = Job(filename=filename, status="Parsing")
                db.add(job)
                db.commit()
                db.refresh(job)
            except IntegrityError:
                db.rollback()
                # Concurrent insert occurred, retrieve the job inserted by the other thread
                job = db.query(Job).filter(Job.filename == filename).first()
                if job:
                    job.status = "Parsing"
                    job.error_message = None
                    db.commit()
                else:
                    logger.error(f"IntegrityError on insert for {filename}, but job query returned None")
                    return None
        else:
            job.status = "Parsing"
            job.error_message = None
            db.commit()

        try:
            job.oma_data = oma_content
            
            # 2. Parse OMA
            parsed_data = OMAParser.parse_file(oma_content)
            job.parsed_json = parsed_data
            
            # Extract main tags
            job.job_id = str(parsed_data.get("JOB", f"JOB-{job.id}"))
            job.eye = str(parsed_data.get("EYE", "R"))  # Default to Right if missing
            
            # Associate jobs and create/update OrderFlow state machine
            if job.job_id:
                order_flow = db.query(OrderFlow).filter(OrderFlow.job_id == job.job_id).first()
                if not order_flow:
                    order_flow = OrderFlow(
                        job_id=job.job_id,
                        state="WAITING_RIGHT_LENS"
                    )
                    db.add(order_flow)
                    db.commit()
                    db.refresh(order_flow)
                
                # Link lens jobs
                if job.eye in ["R", "OD"]:
                    order_flow.od_job_id = job.id
                    order_flow.od_status = "PENDING"
                    order_flow.state = "WAITING_RIGHT_LENS"
                elif job.eye in ["L", "OS", "OE"]:
                    order_flow.oe_job_id = job.id
                    order_flow.oe_status = "PENDING"
                    # If OD is missing, start with WAITING_LEFT_LENS
                    if not order_flow.od_job_id:
                        order_flow.state = "WAITING_LEFT_LENS"
                db.commit()

            job.lens_name = parsed_data.get("LNAM", "Freeform Lens")
            job.axis = float(parsed_data.get("AXIS", 0.0))
            job.addition = float(parsed_data.get("ADD", 2.00))  # Default addition
            job.diameter = float(parsed_data.get("LDG", 70.0))  # Default 70mm diameter
            
            # Prism tags
            job.prism = float(parsed_data.get("PRISM", 0.0))
            job.prism_base = float(parsed_data.get("PBASE", 0.0))
            
            # 3. Match against active lens templates
            # We look for a template whose name is a case-insensitive substring of job.lens_name
            # or where job.lens_name is a case-insensitive substring of template.name.
            matched_template = None
            if job.lens_name:
                active_templates = db.query(LensTemplate).filter(LensTemplate.is_active == 1).all()
                for template in active_templates:
                    if (template.name.lower() in job.lens_name.lower()) or (job.lens_name.lower() in template.name.lower()):
                        matched_template = template
                        break
            
            # Define default geometric parameters
            t_offset_x = 0.0
            t_offset_y = 0.0
            t_rotation = 0.0
            fc_dist = 4.0
            ref_point = "PRP"
            
            if matched_template:
                job.template_id = matched_template.id
                t_offset_x = matched_template.offset_x
                t_offset_y = matched_template.offset_y
                t_rotation = matched_template.rotation
                fc_dist = matched_template.fitting_cross_dist
                ref_point = matched_template.reference_point
                log_system_event(db, "INFO", f"Automatic template applied: '{matched_template.name}' for lens '{job.lens_name}' (ID: {matched_template.id})")
            else:
                job.template_id = None
                log_system_event(db, "WARNING", f"No active lens template matches '{job.lens_name}'. Applying system defaults.")

            job.status = "Calculating"
            db.commit()
            
            # 4. Retrieve active calibration offsets
            cal = get_or_create_calibration(db)
            calibration_dict = {
                "offset_x": cal.offset_x,
                "offset_y": cal.offset_y,
                "scale_x": cal.scale_x,
                "scale_y": cal.scale_y,
                "rotation": cal.rotation
            }
            
            # 5. Geometric Calculations with Curvature Correcting Math
            shape_coords = parsed_data.get("shape_coordinates", [])
            geo_results = OphthalmicGeoEngine.calculate_geometry(
                shape_coords=shape_coords,
                eye=job.eye,
                axis=job.axis,
                addition=job.addition,
                calibration=calibration_dict,
                template_offset_x=t_offset_x,
                template_offset_y=t_offset_y,
                template_rotation=t_rotation,
                fitting_cross_dist=fc_dist,
                reference_point=ref_point
            )
            
            # Inject standard Job metadata
            geo_results["markings"]["job_id"] = job.job_id
            
            job.geometry_json = geo_results
            
            # 5. Generate laser files
            svg_content = LaserPathGenerator.generate_svg(geo_results)
            gcode_content = LaserPathGenerator.generate_gcode(geo_results)
            lbrn2_content = LaserPathGenerator.generate_lbrn2(geo_results)
            
            # Write to outputs directory
            svg_filename = f"{Path(filename).stem}_preview.svg"
            gcode_filename = f"{Path(filename).stem}_laser.gcode"
            lbrn2_filename = f"{Path(filename).stem}_lightburn.lbrn2"
            
            svg_file_path = OUTPUT_DIR / svg_filename
            gcode_file_path = OUTPUT_DIR / gcode_filename
            lbrn2_file_path = OUTPUT_DIR / lbrn2_filename
            
            with open(svg_file_path, "w", encoding="utf-8") as f:
                f.write(svg_content)
            with open(gcode_file_path, "w", encoding="utf-8") as f:
                f.write(gcode_content)
            with open(lbrn2_file_path, "w", encoding="utf-8") as f:
                f.write(lbrn2_content)
                
            job.svg_path = str(svg_file_path)
            job.gcode_path = str(gcode_file_path)
            job.lbrn2_path = str(lbrn2_file_path)
            
            # Success
            job.status = "Ready"
            db.commit()
            log_system_event(db, "SUCCESS", f"Successfully completed calculations and files for {filename}")
            
        except Exception as e:
            db.rollback()
            job.status = "Failed"
            job.error_message = str(e)
            db.commit()
            log_system_event(db, "ERROR", f"Failed processing {filename}: {e}")
            
        return job
    finally:
        with processing_files_lock:
            processing_files.discard(filename)


class OMAFolderWatcher(FileSystemEventHandler):
    """Watchdog events handler listening to OMA file creations and modifications."""
    
    def handle_event(self, event):
        if event.is_directory:
            return
            
        filepath = event.src_path
        filename = os.path.basename(filepath)
        
        # Filter OMA file extension (.oma / .txt / .jdf)
        if filepath.lower().endswith(('.oma', '.txt')):
            db = SessionLocal()
            try:
                process_job_pipeline(db, filepath, filename)
            finally:
                db.close()

    def on_created(self, event):
        self.handle_event(event)

    def on_modified(self, event):
        self.handle_event(event)


class FolderMonitorManager:
    """Manages starting/stopping the watchdog directory thread."""
    def __init__(self):
        self.observer = None
        
    def start_monitoring(self):
        # Create database tables if they do not exist yet
        Base.metadata.create_all(bind=engine)
        
        db = SessionLocal()
        try:
            get_or_create_calibration(db)
            
            # Reset stuck jobs on startup to prevent infinite 'Calculating/Parsing/Streaming' states
            stuck_jobs = db.query(Job).filter(
                (Job.status.in_(["Parsing", "Calculating"])) | 
                (Job.status.like("Streaming%"))
            ).all()
            if stuck_jobs:
                for sj in stuck_jobs:
                    sj.status = "Failed"
                    sj.error_message = "Sistema reiniciado durante o processamento ou transmissão."
                db.commit()
                log_system_event(db, "WARNING", f"Reset {len(stuck_jobs)} stuck jobs to Failed status on startup.")

            log_system_event(db, "INFO", f"Initializing monitor. Watching directory: {WATCH_DIR}")
            
            # Startup Scan: Process any existing files in watch_dir that aren't in the DB yet
            if os.path.exists(WATCH_DIR):
                for filename in os.listdir(WATCH_DIR):
                    if filename.lower().endswith(('.oma', '.txt')):
                        filepath = os.path.join(WATCH_DIR, filename)
                        existing_job = db.query(Job).filter(Job.filename == filename).first()
                        if not existing_job:
                            log_system_event(db, "INFO", f"Found existing unprocessed OMA file on startup: {filename}")
                            process_job_pipeline(db, filepath, filename)
        except Exception as e:
            logger.error(f"Startup folder scanning failed: {e}")
        finally:
            db.close()
            
        event_handler = OMAFolderWatcher()
        self.observer = Observer()
        self.observer.schedule(event_handler, path=str(WATCH_DIR), recursive=False)
        self.observer.start()
        
    def stop_monitoring(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("Folder monitoring watchdog stopped.")
