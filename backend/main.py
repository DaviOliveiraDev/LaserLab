import os
import math
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging
from contextlib import asynccontextmanager

from backend.config import WATCH_DIR, OUTPUT_DIR, LASER_SERIAL_PORT, LASER_BAUDRATE
from backend.database import engine, Base, get_db, SessionLocal
from backend.models import Job, Calibration, SystemLog, LensTemplate, TemplateHistory
from backend.schemas import (
    JobResponse, CalibrationBase, CalibrationResponse, 
    SystemLogResponse, SystemStatusResponse,
    LensTemplateCreate, LensTemplateResponse, TemplateHistoryResponse,
    VirtualMachineStatusResponse, SimulatorAlarmRequest
)
from backend.monitor.folder_monitor import (
    FolderMonitorManager, process_job_pipeline, 
    log_system_event, get_or_create_calibration
)
from backend.laser.laser_integration import GRBLSerialStreamer
from backend.laser.simulator import virtual_laser


# Setup logging
logger = logging.getLogger(__name__)

# Active background task tracking for laser streaming
active_streamers: Dict[int, GRBLSerialStreamer] = {}

# Folder monitor lifecycle manager
monitor_manager = FolderMonitorManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    Base.metadata.create_all(bind=engine)
    monitor_manager.start_monitoring()
    yield
    # Shutdown actions
    monitor_manager.stop_monitoring()
    # Cancel any active laser streams
    for streamer in active_streamers.values():
        streamer.stop()

app = FastAPI(
    title="Ophthalmic Lens Laser Engraving Automation Server",
    description="Backend service for OMA parsing, geometric analysis, and GRBL laser integration.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend dashboard connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in MVP local setup
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Endpoints -----------------

@app.get("/api/system/status", response_model=SystemStatusResponse)
def get_system_status(db: Session = Depends(get_db)):
    """Fetch real-time physical states of the software monitor and laser connection."""
    cal = get_or_create_calibration(db)
    job_count = db.query(Job).count()
    
    # Check if mock serial or active COM
    laser_conn = False
    if LASER_SERIAL_PORT != "COM_MOCK":
        try:
            import serial
            # Try a dry connect to see if the port exists/is free
            ser = serial.Serial(LASER_SERIAL_PORT, timeout=0.1)
            ser.close()
            laser_conn = True
        except Exception:
            laser_conn = False
    else:
        laser_conn = True  # Simulated connection always true

    return {
        "monitoring": monitor_manager.observer is not None and monitor_manager.observer.is_alive(),
        "laser_connected": laser_conn,
        "laser_port": LASER_SERIAL_PORT,
        "job_queue_count": job_count,
        "calibration": {
            "offset_x": cal.offset_x,
            "offset_y": cal.offset_y,
            "scale_x": cal.scale_x,
            "scale_y": cal.scale_y,
            "rotation": cal.rotation
        }
    }


@app.get("/api/jobs", response_model=List[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    """Returns the list of processed jobs sorted by creation date."""
    return db.query(Job).order_by(Job.created_at.desc()).all()


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    """Fetch comprehensive metadata of a single job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/preview")
def get_job_preview_svg(job_id: int, db: Session = Depends(get_db)):
    """Serves the generated SVG lens preview with the correct vector MIME type."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or not job.svg_path:
        raise HTTPException(status_code=404, detail="SVG preview file not found for this job")
    
    if os.path.exists(job.svg_path):
        with open(job.svg_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content=content, media_type="image/svg+xml")
    
    raise HTTPException(status_code=404, detail="Physical SVG file missing on disk")


@app.post("/api/jobs/{job_id}/reprocess", response_model=JobResponse)
def reprocess_job(job_id: int, db: Session = Depends(get_db)):
    """Reprocesses a job, recalculating laser points using newly saved calibration configurations."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Locate original file in monitored directory or write raw OMA data back to it
    oma_filename = job.filename
    target_path = WATCH_DIR / oma_filename
    
    if not os.path.exists(target_path) and job.oma_data:
        # Re-create file if deleted
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(job.oma_data)
            
    updated_job = process_job_pipeline(db, str(target_path), oma_filename, force_reprocess=True)
    return updated_job


@app.get("/api/calibration", response_model=CalibrationResponse)
def get_calibration(db: Session = Depends(get_db)):
    """Fetch active calibration factors."""
    return get_or_create_calibration(db)


@app.post("/api/calibration", response_model=CalibrationResponse)
def update_calibration(cal_data: CalibrationBase, db: Session = Depends(get_db)):
    """Updates physical scale and rotation offsets and triggers logs notification."""
    cal = get_or_create_calibration(db)
    cal.offset_x = cal_data.offset_x
    cal.offset_y = cal_data.offset_y
    cal.scale_x = cal_data.scale_x
    cal.scale_y = cal_data.scale_y
    cal.rotation = cal_data.rotation
    db.commit()
    db.refresh(cal)
    
    log_system_event(
        db, "WARNING", 
        f"Calibration offsets updated: Offset=({cal.offset_x}, {cal.offset_y}) Rot={cal.rotation}° Scale=({cal.scale_x}, {cal.scale_y})"
    )
    return cal


@app.get("/api/logs", response_model=List[SystemLogResponse])
def get_logs(db: Session = Depends(get_db), limit: int = 40):
    """Retrieve operational logging details."""
    return db.query(SystemLog).order_by(SystemLog.timestamp.desc()).limit(limit).all()


# ----------------- Laser Control & Streaming -----------------

def background_laser_stream(job_id: int, gcode_text: str, port: str, baudrate: int):
    """Worker task designed to stream lines in background with real-time simulator integration."""
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        return

    streamer = active_streamers.get(job_id)
    if not streamer:
        db.close()
        return

    # Count actual G-code commands (excluding empty and comment lines)
    gcode_lines = [line.strip() for line in gcode_text.splitlines() if line.strip() and not line.startswith(";")]
    total_lines = len(gcode_lines)

    try:
        # Start virtual machine job tracking
        virtual_laser.start_job(job_id, total_lines)
    except Exception as e:
        logger.error(f"Could not start virtual laser job: {e}")
        job.status = "Failed"
        job.error_message = f"Hardware status check failed: {e}"
        db.commit()
        db.close()
        return
        
    def progress_update(percentage: float):
        # Update processing status in SQLite
        db_updater = SessionLocal()
        try:
            target_job = db_updater.query(Job).filter(Job.id == job_id).first()
            if target_job:
                target_job.status = f"Streaming: {int(percentage)}%"
                db_updater.commit()
        finally:
            db_updater.close()

    def line_callback(index: int, line_content: str) -> bool:
        try:
            # Updates simulator state (checks for alarm safety interrupts inside simulator)
            virtual_laser.update_progress(index + 1, line_content)
            return True
        except Exception as ex:
            logger.error(f"Laser safety interrupt triggered: {ex}")
            return False

    try:
        log_system_event(db, "INFO", f"Initiating laser G-code transmission for Job ID: {job.job_id}")
        success = streamer.stream_gcode(
            gcode_text, 
            progress_callback=progress_update,
            line_callback=line_callback
        )
        
        # Read absolute target state
        db.refresh(job)
        
        # Check if failed because of virtual alarms
        virtual_laser.update_telemetry()
        if virtual_laser.door_open_alarm:
            success = False
            job.status = "Failed"
            job.error_message = "ALERTA CRÍTICO: Gravação interrompida! Sensor detectou a abertura da porta de segurança (Safety Door Open)."
            log_system_event(db, "ERROR", f"Safety door opened during laser engraving. Job {job.job_id} aborted.")
        elif virtual_laser.overtemp_alarm:
            success = False
            job.status = "Failed"
            job.error_message = f"ALERTA CRÍTICO: Gravação interrompida! Sobreaquecimento detectado no diodo laser (Temperatura: {virtual_laser.temperature:.1f}°C > limite de 65°C)."
            log_system_event(db, "ERROR", f"Diode temperature threshold exceeded. Job {job.job_id} aborted.")
        elif not success:
            job.status = "Failed"
            if not job.error_message or "manually aborted" not in job.error_message:
                job.error_message = "Transmissão interrompida pelo operador ou falha de comunicação serial."
            log_system_event(db, "ERROR", f"Streaming failed or cancelled for Job {job.job_id}.")
            
        if success:
            job.status = "Success"
            virtual_laser.finish_job()
            log_system_event(db, "SUCCESS", f"Finished engraving progressive markings on job {job.job_id}")
        else:
            # Inform virtual laser simulator of abort
            if not virtual_laser.door_open_alarm and not virtual_laser.overtemp_alarm:
                virtual_laser.finish_job()
            
        db.commit()
    except Exception as e:
        db.rollback()
        job.status = "Failed"
        job.error_message = str(e)
        db.commit()
        virtual_laser.finish_job()
        log_system_event(db, "ERROR", f"Critical laser communication crash on job {job.job_id}: {e}")
    finally:
        active_streamers.pop(job_id, None)
        db.close()


@app.post("/api/jobs/{job_id}/stream")
def stream_job_to_laser(job_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Wakes the laser up and streams the G-code tools in a safe, non-blocking background queue."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status.startswith("Streaming"):
        raise HTTPException(status_code=400, detail="This job is already actively streaming to hardware.")

    if not job.gcode_path or not os.path.exists(job.gcode_path):
        raise HTTPException(status_code=400, detail="No calculated G-code is available to stream. Reprocess first.")

    with open(job.gcode_path, "r", encoding="utf-8") as f:
        gcode_text = f.read()

    # Create streamer instance
    streamer = GRBLSerialStreamer(port=LASER_SERIAL_PORT, baudrate=LASER_BAUDRATE)
    active_streamers[job_id] = streamer
    
    job.status = "Streaming: 0%"
    db.commit()

    background_tasks.add_task(
        background_laser_stream,
        job_id=job_id,
        gcode_text=gcode_text,
        port=LASER_SERIAL_PORT,
        baudrate=LASER_BAUDRATE
    )
    return {"message": "Laser streaming initialized.", "job_id": job_id}


@app.post("/api/jobs/{job_id}/stop")
def stop_job_streaming(job_id: int, db: Session = Depends(get_db)):
    """Aborts physical laser transmission immediately."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    streamer = active_streamers.pop(job_id, None)
    if streamer:
        streamer.stop()
        job.status = "Failed"
        job.error_message = "Laser engraving stream manually aborted by operator."
        db.commit()
        log_system_event(db, "WARNING", f"Operator manually cancelled laser burn sequence on: {job.job_id}")
        return {"message": "Laser transmission aborted."}
        
    return {"message": "No active serial stream found for this job."}


# ----------------- Mock OMA Creator (For Testing) -----------------

@app.post("/api/system/mock-job")
def create_mock_oma_job(db: Session = Depends(get_db)):
    """
    Utility endpoint that programmatically dumps a high-fidelity OMA file
    containing a custom physical TRCFMT lens shape directly into the WATCH_DIR.
    Simulates real-world laboratory workflow instantly!
    """
    import random
    job_num = random.randint(10000, 99999)
    filename = f"job_{job_num}.oma"
    filepath = WATCH_DIR / filename
    
    # Generate custom OMA string with complex shape points (simulated left or right lens)
    eye = random.choice(["R", "L"])
    axis = random.choice([0, 45, 90, 135, 180])
    addition = random.choice([1.50, 2.00, 2.50, 3.00])
    
    # Construct a slightly oval shaped trace (width 70mm, height 60mm)
    shape_lines = []
    for i in range(360):
        rad = math.radians(i)
        # Oval math: base radius 32mm with variation
        r_mm = 32.0 + 3.0 * math.cos(rad * 2.0)
        # OMA uses 0.01 mm units (multiply by 100)
        r_oma = int(r_mm * 100)
        shape_lines.append(str(r_oma))
        
    trcfmt_str = f"{eye};360;1.0;1.0;R;{';'.join(shape_lines)}"
    
    oma_lines = [
        f"JOB={job_num}",
        f"EYE={eye}",
        f"LNAM=Freeform progressive MVP",
        f"LDG=72.0",
        f"AXIS={axis}",
        f"ADD={addition:.2f}",
        f"PRISM=0.0",
        f"PBASE=0.0",
        f"TRCFMT={trcfmt_str}"
    ]
    
    oma_text = "\n".join(oma_lines)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(oma_text)
        
    log_system_event(db, "INFO", f"Programmatically injected mock OMA file: {filename}")
    
    job = process_job_pipeline(db, str(filepath), filename, force_reprocess=True)
    job_data = JobResponse.model_validate(job).dict()
    return {"message": "Mock OMA Job created", "filename": filename, "job": job_data}


# ----------------- Lens Template Database Endpoints -----------------

@app.get("/api/templates", response_model=List[LensTemplateResponse])
def list_templates(search: Optional[str] = None, db: Session = Depends(get_db)):
    """Fetch registered lens templates, optionally filtered by name/manufacturer/type."""
    query = db.query(LensTemplate)
    if search:
        query = query.filter(
            (LensTemplate.name.ilike(f"%{search}%")) |
            (LensTemplate.manufacturer.ilike(f"%{search}%")) |
            (LensTemplate.lens_type.ilike(f"%{search}%"))
        )
    return query.order_by(LensTemplate.created_at.desc()).all()


@app.post("/api/templates", response_model=LensTemplateResponse)
def create_template(template_in: LensTemplateCreate, db: Session = Depends(get_db)):
    """Creates a new ophthalmic lens design template and logs event to audit history."""
    existing = db.query(LensTemplate).filter(LensTemplate.name == template_in.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="A template with this model name already exists.")
    
    template = LensTemplate(**template_in.dict())
    db.add(template)
    db.commit()
    db.refresh(template)
    
    # Log to History
    history = TemplateHistory(
        template_id=template.id,
        template_name=template.name,
        action="CREATE",
        changed_fields=template_in.dict(),
    )
    db.add(history)
    db.commit()
    
    log_system_event(db, "SUCCESS", f"Lens template '{template.name}' successfully registered.")
    return template


@app.put("/api/templates/{id}", response_model=LensTemplateResponse)
def update_template(id: int, template_in: LensTemplateCreate, db: Session = Depends(get_db)):
    """Updates physical engraving coordinates and shifts, auditing detailed diff parameters."""
    template = db.query(LensTemplate).filter(LensTemplate.id == id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Check uniqueness of name if changed
    if template.name != template_in.name:
        existing = db.query(LensTemplate).filter(LensTemplate.name == template_in.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="A template with this model name already exists.")
    
    # Track diff
    diff = {}
    old_data = {
        "name": template.name,
        "manufacturer": template.manufacturer,
        "lens_type": template.lens_type,
        "offset_x": template.offset_x,
        "offset_y": template.offset_y,
        "rotation": template.rotation,
        "fitting_cross_dist": template.fitting_cross_dist,
        "reference_point": template.reference_point,
        "technical_notes": template.technical_notes,
        "is_active": template.is_active
    }
    new_data = template_in.dict()
    for key, val in new_data.items():
        if old_data.get(key) != val:
            diff[key] = [old_data.get(key), val]
              
    # Apply updates
    for key, val in new_data.items():
        setattr(template, key, val)
          
    db.commit()
    db.refresh(template)
    
    # Log history if there are differences
    if diff:
        history = TemplateHistory(
            template_id=template.id,
            template_name=template.name,
            action="UPDATE",
            changed_fields=diff,
        )
        db.add(history)
        db.commit()
          
    log_system_event(db, "INFO", f"Lens template '{template.name}' updated by operator.")
    return template


@app.post("/api/templates/{id}/duplicate", response_model=LensTemplateResponse)
def duplicate_template(id: int, db: Session = Depends(get_db)):
    """Clones an existing template, incrementing names safely to prevent database collisions."""
    template = db.query(LensTemplate).filter(LensTemplate.id == id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
          
    # Find a unique duplicated name
    base_name = f"{template.name} (Cópia)"
    suffix = 1
    new_name = base_name
    while db.query(LensTemplate).filter(LensTemplate.name == new_name).first():
        new_name = f"{base_name} {suffix}"
        suffix += 1
          
    new_template = LensTemplate(
        name=new_name,
        manufacturer=template.manufacturer,
        lens_type=template.lens_type,
        offset_x=template.offset_x,
        offset_y=template.offset_y,
        rotation=template.rotation,
        fitting_cross_dist=template.fitting_cross_dist,
        reference_point=template.reference_point,
        technical_notes=f"Copiado de {template.name}. " + (template.technical_notes or ""),
        is_active=1
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    
    # Log history
    history = TemplateHistory(
        template_id=new_template.id,
        template_name=new_template.name,
        action="DUPLICATE",
        changed_fields={"source_template_id": template.id, "source_template_name": template.name}
    )
    db.add(history)
    db.commit()
      
    log_system_event(db, "SUCCESS", f"Duplicated template '{template.name}' as '{new_template.name}'")
    return new_template


@app.post("/api/templates/{id}/toggle", response_model=LensTemplateResponse)
def toggle_template_status(id: int, db: Session = Depends(get_db)):
    """Toggles status (active/inactive) preventing template automatic matches on future OMA files."""
    template = db.query(LensTemplate).filter(LensTemplate.id == id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
          
    template.is_active = 0 if template.is_active == 1 else 1
    db.commit()
    db.refresh(template)
      
    action = "ACTIVATE" if template.is_active == 1 else "DEACTIVATE"
    # Log history
    history = TemplateHistory(
        template_id=template.id,
        template_name=template.name,
        action=action,
        changed_fields={"is_active": template.is_active}
    )
    db.add(history)
    db.commit()
      
    log_system_event(db, "WARNING" if action == "DEACTIVATE" else "SUCCESS", f"Template '{template.name}' set to {'Active' if template.is_active == 1 else 'Inactive'}")
    return template


@app.get("/api/templates/{id}/history", response_model=List[TemplateHistoryResponse])
def get_template_history(id: int, db: Session = Depends(get_db)):
    """Fetches operator change logs history for audit tracking of a specific template."""
    return db.query(TemplateHistory).filter(TemplateHistory.template_id == id).order_by(TemplateHistory.timestamp.desc()).all()


# ----------------- Laser Simulator Endpoints -----------------

@app.get("/api/jobs/{job_id}/gcode")
def get_job_gcode(job_id: int, db: Session = Depends(get_db)):
    """Serves the generated G-code text of a single job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or not job.gcode_path:
        raise HTTPException(status_code=404, detail="G-code file not found for this job")
    
    if os.path.exists(job.gcode_path):
        with open(job.gcode_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content=content, media_type="text/plain")
    
    raise HTTPException(status_code=404, detail="Physical G-code file missing on disk")


@app.get("/api/simulator/machine", response_model=VirtualMachineStatusResponse)
def get_simulator_status():
    """Fetches real-time sensor metrics and status of the virtual laser machine."""
    return virtual_laser.get_status_dict()


@app.post("/api/simulator/machine/alarm", response_model=VirtualMachineStatusResponse)
def inject_simulator_alarm(req: SimulatorAlarmRequest, db: Session = Depends(get_db)):
    """Injects or toggles a simulated hardware PLC alarm (safety door open, diode temp drop)."""
    virtual_laser.set_alarm(req.alarm_name, req.value)
    
    status_label = "TRIGGERED" if req.value else "CLEARED"
    alarm_labels = {
        "door_open": "SAFETY DOOR OPEN INTERRUPT",
        "overtemp": "DIODE OVERTEMPERATURE ALARM (>65°C)",
        "power_drop": "LASER TUBE POWER DROP"
    }
    label = alarm_labels.get(req.alarm_name, req.alarm_name.upper())
    
    log_system_event(
        db, 
        "ERROR" if req.value else "SUCCESS", 
        f"PLC Simulator Alarm {status_label}: {label}"
    )
    return virtual_laser.get_status_dict()


@app.post("/api/simulator/machine/reset", response_model=VirtualMachineStatusResponse)
def reset_simulator_alarms(db: Session = Depends(get_db)):
    """Resets all simulated hardware warnings and unlocks the laser simulator."""
    virtual_laser.reset_alarms()
    log_system_event(db, "SUCCESS", "Safety system reset. All PLC alarms cleared. Machine is READY.")
    return virtual_laser.get_status_dict()

