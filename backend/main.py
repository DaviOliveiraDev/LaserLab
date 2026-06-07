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
from backend.models import Job, Calibration, SystemLog, LensTemplate, TemplateHistory, OrderFlow, ProductionLog
from backend.schemas import (
    JobResponse, CalibrationBase, CalibrationResponse, 
    SystemLogResponse, SystemStatusResponse,
    LensTemplateCreate, LensTemplateResponse, TemplateHistoryResponse,
    VirtualMachineStatusResponse, SimulatorAlarmRequest,
    OrderFlowResponse, ProductionLogResponse
)
from backend.monitor.folder_monitor import (
    FolderMonitorManager, process_job_pipeline, 
    log_system_event, get_or_create_calibration, log_production_event
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

def background_laser_stream(job_id: int, gcode_text: str, port: str, baudrate: int, start_line_index: int = 0):
    """Worker task designed to stream G-code in background with real-time simulator integration."""
    import datetime
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        return

    streamer = active_streamers.get(job_id)
    if not streamer:
        db.close()
        return

    # Count actual G-code commands
    gcode_lines = [line.strip() for line in gcode_text.splitlines() if line.strip() and not line.startswith(";")]
    total_lines = len(gcode_lines)

    try:
        # Start virtual machine job tracking
        virtual_laser.start_job(job_id, total_lines, start_line_index)
    except Exception as e:
        logger.error(f"Could not start virtual laser job: {e}")
        job.status = "Failed"
        job.error_message = f"Hardware status check failed: {e}"
        db.commit()
        db.close()
        return
        
    def progress_update(percentage: float):
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
            virtual_laser.update_progress(index + 1, line_content)
            return True
        except Exception as ex:
            logger.error(f"Laser safety interrupt triggered: {ex}")
            return False

    try:
        log_system_event(db, "INFO", f"Initiating laser G-code transmission for Job ID: {job.job_id}")
        
        # Determine lens side
        lens_side = "OD" if job.eye in ["R", "OD"] else "OE"
        
        # Log initial positioned and start events (only on initial run)
        if start_line_index == 0:
            log_production_event(db, job.job_id, "LENS_POSITIONED", f"Lente {lens_side} posicionada no suporte.", lens_side)
            log_production_event(db, job.job_id, "ENGRAVING_STARTED", f"Início da gravação da Lente {lens_side}.", lens_side)

        success = streamer.stream_gcode(
            gcode_text, 
            progress_callback=progress_update,
            line_callback=line_callback,
            start_line_index=start_line_index
        )
        
        # Read absolute target state
        db.refresh(job)
        
        # Calculate time spent on engraving in this cycle
        lines_processed = virtual_laser.current_gcode_index - start_line_index
        time_seconds = max(0.0, lines_processed * 0.08)
        
        # Fetch OrderFlow and update time & activity
        order_flow = None
        if job.job_id:
            db.expire_all()
            order_flow = db.query(OrderFlow).filter(OrderFlow.job_id == job.job_id).first()
            if order_flow:
                order_flow.engraving_time_seconds += time_seconds
                order_flow.last_activity = datetime.datetime.utcnow()

        virtual_laser.update_telemetry()
        if virtual_laser.door_open_alarm or virtual_laser.overtemp_alarm:
            success = False
            job.status = "Failed"
            
            if virtual_laser.door_open_alarm:
                job.error_message = "ALERTA CRÍTICO: Gravação interrompida! Sensor detectou a abertura da porta de segurança (Safety Door Open)."
                event_msg = "ALERTA CRÍTICO: Porta de segurança aberta durante a gravação."
            else:
                job.error_message = f"ALERTA CRÍTICO: Gravação interrompida! Sobreaquecimento detectado no diodo laser (Temperatura: {virtual_laser.temperature:.1f}°C > limite de 65°C)."
                event_msg = f"ALERTA CRÍTICO: Sobreaquecimento do diodo ({virtual_laser.temperature:.1f}°C)."
                
            log_system_event(db, "ERROR", f"Safety alarm triggered. Job {job.job_id} aborted.")
            
            if order_flow:
                order_flow.state = "ERROR"
                order_flow.error_count += 1
                if lens_side == "OD":
                    order_flow.od_status = "FAILED"
                else:
                    order_flow.oe_status = "FAILED"
                db.commit()
                log_production_event(db, job.job_id, "ERROR", event_msg, lens_side)

        elif not success:
            job.status = "Failed"
            
            # Pause vs Abort/Cancel
            if order_flow and order_flow.state == "PAUSED":
                job.error_message = "Gravação pausada pelo operador."
                # Production log is already written inside the pause API endpoint
            else:
                job.error_message = "Transmissão interrompida pelo operador."
                if order_flow:
                    if order_flow.state != "CANCELLED":
                        order_flow.state = "CANCELLED"
                        order_flow.end_time = datetime.datetime.utcnow()
                    if lens_side == "OD":
                        order_flow.od_status = "FAILED"
                    else:
                        order_flow.oe_status = "FAILED"
                    db.commit()
                log_production_event(db, job.job_id, "ENGRAVING_CANCELLED", "Gravação cancelada pelo operador.", lens_side)
                log_system_event(db, "ERROR", f"Streaming failed or cancelled for Job {job.job_id}.")
            
        if success:
            job.status = "Success"
            virtual_laser.finish_job()
            log_system_event(db, "SUCCESS", f"Finished engraving progressive markings on job {job.job_id}")
            
            if order_flow:
                if lens_side == "OD":
                    order_flow.state = "WAITING_RIGHT_REMOVAL"
                    order_flow.od_status = "COMPLETED"
                else:
                    order_flow.state = "WAITING_LEFT_REMOVAL"
                    order_flow.oe_status = "COMPLETED"
                db.commit()
                log_production_event(db, job.job_id, "ENGRAVING_COMPLETED", f"Gravação da Lente {lens_side} concluída.", lens_side)
        else:
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

def _trigger_laser_stream(job_id: int, start_line_index: int, background_tasks: BackgroundTasks, db: Session):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Lente não encontrada")
        
    if not job.gcode_path or not os.path.exists(job.gcode_path):
        raise HTTPException(status_code=400, detail="G-code não calculado para esta lente. Processe primeiro.")

    with open(job.gcode_path, "r", encoding="utf-8") as f:
        gcode_text = f.read()

    old_streamer = active_streamers.pop(job_id, None)
    if old_streamer:
        old_streamer.stop()

    streamer = GRBLSerialStreamer(port=LASER_SERIAL_PORT, baudrate=LASER_BAUDRATE)
    active_streamers[job_id] = streamer
    
    # Calculate G-code lines to estimate progress
    lines = [line.strip() for line in gcode_text.splitlines() if line.strip() and not line.startswith(";")]
    total_lines = len(lines)
    progress_pct = int((start_line_index / total_lines) * 100) if total_lines > 0 else 0
    
    job.status = f"Streaming: {progress_pct}%"
    db.commit()

    background_tasks.add_task(
        background_laser_stream,
        job_id=job_id,
        gcode_text=gcode_text,
        port=LASER_SERIAL_PORT,
        baudrate=LASER_BAUDRATE,
        start_line_index=start_line_index
    )


@app.post("/api/jobs/{job_id}/stream")
def stream_job_to_laser(job_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Wakes the laser up and streams the G-code tools in a safe, non-blocking background queue."""
    _trigger_laser_stream(job_id, 0, background_tasks, db)
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


# ----------------- Guided Order Flow State Machine Endpoints -----------------

@app.get("/api/orders", response_model=List[OrderFlowResponse])
def list_order_flows(db: Session = Depends(get_db)):
    flows = db.query(OrderFlow).order_by(OrderFlow.created_at.desc()).all()
    for flow in flows:
        flow.logs = db.query(ProductionLog).filter(ProductionLog.job_id == flow.job_id).order_by(ProductionLog.timestamp.asc()).all()
    return flows

@app.get("/api/orders/{job_id}/flow", response_model=OrderFlowResponse)
def get_order_flow(job_id: str, test_timeout: bool = False, db: Session = Depends(get_db)):
    import datetime
    order_flow = db.query(OrderFlow).filter(OrderFlow.job_id == job_id).first()
    if not order_flow:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if job:
            order_flow = OrderFlow(
                job_id=job_id,
                state="WAITING_RIGHT_LENS"
            )
            db.add(order_flow)
            db.commit()
            db.refresh(order_flow)
            
            jobs = db.query(Job).filter(Job.job_id == job_id).all()
            for j in jobs:
                if j.eye in ["R", "OD"]:
                    order_flow.od_job_id = j.id
                    order_flow.od_status = "PENDING"
                elif j.eye in ["L", "OS", "OE"]:
                    order_flow.oe_job_id = j.id
                    order_flow.oe_status = "PENDING"
            
            if not order_flow.od_job_id and order_flow.oe_job_id:
                order_flow.state = "WAITING_LEFT_LENS"
            db.commit()
        else:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
            
    # Timeout check (inactivity alert)
    if order_flow.state in ["WAITING_RIGHT_LENS", "WAITING_RIGHT_REMOVAL", "WAITING_LEFT_LENS", "WAITING_LEFT_REMOVAL"]:
        now = datetime.datetime.utcnow()
        elapsed = (now - order_flow.last_activity).total_seconds()
        threshold = 30.0 if test_timeout else 300.0
        
        if elapsed > threshold:
            lens_side = "OD" if order_flow.state in ["WAITING_RIGHT_LENS", "WAITING_RIGHT_REMOVAL"] else "OE"
            log_production_event(
                db, job_id, "ERROR",
                f"Tempo de inatividade excedido: Operador inativo por mais de {int(threshold/60) if threshold >= 60 else int(threshold)}s nesta etapa.",
                lens_side
            )
            order_flow.last_activity = now
            db.commit()
            
    logs = db.query(ProductionLog).filter(ProductionLog.job_id == job_id).order_by(ProductionLog.timestamp.asc()).all()
    order_flow.logs = logs
    return order_flow


@app.post("/api/orders/{job_id}/flow/start", response_model=OrderFlowResponse)
def start_order_flow_engraving(job_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    import datetime
    order_flow = db.query(OrderFlow).filter(OrderFlow.job_id == job_id).first()
    if not order_flow:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
        
    if order_flow.state == "WAITING_RIGHT_LENS":
        if not order_flow.od_job_id:
            order_flow.state = "WAITING_LEFT_LENS"
            order_flow.od_status = "SKIPPED"
            db.commit()
            log_production_event(db, job_id, "LENS_SKIPPED", "Lente OD não disponível. Pulando para Lente OE.", "OD")
            return order_flow
            
        order_flow.state = "RIGHT_LENS_PROCESSING"
        order_flow.current_lens = "OD"
        order_flow.od_status = "PROCESSING"
        if not order_flow.start_time:
            order_flow.start_time = datetime.datetime.utcnow()
        order_flow.last_activity = datetime.datetime.utcnow()
        db.commit()
        
        _trigger_laser_stream(order_flow.od_job_id, 0, background_tasks, db)
        
    elif order_flow.state == "WAITING_LEFT_LENS":
        if not order_flow.oe_job_id:
            order_flow.state = "COMPLETED"
            order_flow.oe_status = "SKIPPED"
            order_flow.end_time = datetime.datetime.utcnow()
            db.commit()
            log_production_event(db, job_id, "LENS_SKIPPED", "Lente OE não disponível. Pedido concluído.", "OE")
            return order_flow
            
        order_flow.state = "LEFT_LENS_PROCESSING"
        order_flow.current_lens = "OE"
        order_flow.oe_status = "PROCESSING"
        if not order_flow.start_time:
            order_flow.start_time = datetime.datetime.utcnow()
        order_flow.last_activity = datetime.datetime.utcnow()
        db.commit()
        
        _trigger_laser_stream(order_flow.oe_job_id, 0, background_tasks, db)
    else:
        raise HTTPException(status_code=400, detail="Gravação não pode ser iniciada a partir do estado atual.")
        
    logs = db.query(ProductionLog).filter(ProductionLog.job_id == job_id).order_by(ProductionLog.timestamp.asc()).all()
    order_flow.logs = logs
    return order_flow


@app.post("/api/orders/{job_id}/flow/confirm-removal", response_model=OrderFlowResponse)
def confirm_lens_removal(job_id: str, db: Session = Depends(get_db)):
    import datetime
    order_flow = db.query(OrderFlow).filter(OrderFlow.job_id == job_id).first()
    if not order_flow:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
        
    if order_flow.state == "WAITING_RIGHT_REMOVAL":
        log_production_event(db, job_id, "LENS_REMOVED", "Lente OD removida do suporte.", "OD")
        if order_flow.oe_job_id:
            order_flow.state = "WAITING_LEFT_LENS"
            order_flow.current_lens = "OE"
        else:
            order_flow.state = "COMPLETED"
            order_flow.end_time = datetime.datetime.utcnow()
            log_production_event(db, job_id, "LENS_REMOVED", "Nenhuma Lente OE cadastrada. Pedido concluído.", "NONE")
            
        order_flow.last_activity = datetime.datetime.utcnow()
        db.commit()
        
    elif order_flow.state == "WAITING_LEFT_REMOVAL":
        log_production_event(db, job_id, "LENS_REMOVED", "Lente OE removida do suporte. Pedido finalizado.", "OE")
        order_flow.state = "COMPLETED"
        order_flow.end_time = datetime.datetime.utcnow()
        order_flow.last_activity = datetime.datetime.utcnow()
        db.commit()
    else:
        raise HTTPException(status_code=400, detail="Remoção não aplicável no estado atual.")
        
    logs = db.query(ProductionLog).filter(ProductionLog.job_id == job_id).order_by(ProductionLog.timestamp.asc()).all()
    order_flow.logs = logs
    return order_flow


@app.post("/api/orders/{job_id}/flow/skip", response_model=OrderFlowResponse)
def skip_current_lens(job_id: str, db: Session = Depends(get_db)):
    import datetime
    order_flow = db.query(OrderFlow).filter(OrderFlow.job_id == job_id).first()
    if not order_flow:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
        
    lens_side = "OD"
    if order_flow.state in ["WAITING_LEFT_LENS", "LEFT_LENS_PROCESSING", "WAITING_LEFT_REMOVAL"]:
        lens_side = "OE"
        
    # Stop streamer if active
    active_job_id = order_flow.od_job_id if lens_side == "OD" else order_flow.oe_job_id
    if active_job_id:
        streamer = active_streamers.pop(active_job_id, None)
        if streamer:
            streamer.stop()
            virtual_laser.finish_job()
            
    # Mark skipped
    if lens_side == "OD":
        order_flow.od_status = "SKIPPED"
        if order_flow.oe_job_id:
            order_flow.state = "WAITING_LEFT_LENS"
            order_flow.current_lens = "OE"
        else:
            order_flow.state = "COMPLETED"
            order_flow.end_time = datetime.datetime.utcnow()
    else:
        order_flow.oe_status = "SKIPPED"
        order_flow.state = "COMPLETED"
        order_flow.end_time = datetime.datetime.utcnow()
        
    order_flow.skip_count += 1
    order_flow.last_activity = datetime.datetime.utcnow()
    db.commit()
    
    log_production_event(db, job_id, "LENS_SKIPPED", f"Lente {lens_side} ignorada pelo operador.", lens_side)
    
    logs = db.query(ProductionLog).filter(ProductionLog.job_id == job_id).order_by(ProductionLog.timestamp.asc()).all()
    order_flow.logs = logs
    return order_flow


@app.post("/api/orders/{job_id}/flow/pause", response_model=OrderFlowResponse)
def pause_order_flow_engraving(job_id: str, db: Session = Depends(get_db)):
    import datetime
    order_flow = db.query(OrderFlow).filter(OrderFlow.job_id == job_id).first()
    if not order_flow:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
        
    if order_flow.state not in ["RIGHT_LENS_PROCESSING", "LEFT_LENS_PROCESSING"]:
        raise HTTPException(status_code=400, detail="Gravação não está ativa para ser pausada.")
        
    lens_side = "OD" if order_flow.state == "RIGHT_LENS_PROCESSING" else "OE"
    active_job_id = order_flow.od_job_id if lens_side == "OD" else order_flow.oe_job_id
    
    order_flow.state = "PAUSED"
    order_flow.last_stopped_lens = lens_side
    order_flow.pause_count += 1
    order_flow.last_activity = datetime.datetime.utcnow()
    db.commit()
    
    if active_job_id:
        streamer = active_streamers.get(active_job_id)
        if streamer:
            order_flow.last_stopped_index = virtual_laser.current_gcode_index
            db.commit()
            streamer.stop()
            virtual_laser.finish_job()
            
    log_production_event(db, job_id, "ENGRAVING_PAUSED", f"Gravação da Lente {lens_side} pausada pelo operador.", lens_side)
    
    logs = db.query(ProductionLog).filter(ProductionLog.job_id == job_id).order_by(ProductionLog.timestamp.asc()).all()
    order_flow.logs = logs
    return order_flow


@app.post("/api/orders/{job_id}/flow/resume", response_model=OrderFlowResponse)
def resume_order_flow_engraving(job_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    import datetime
    order_flow = db.query(OrderFlow).filter(OrderFlow.job_id == job_id).first()
    if not order_flow:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
        
    if order_flow.state != "PAUSED":
        raise HTTPException(status_code=400, detail="Gravação não está pausada.")
        
    lens_side = order_flow.last_stopped_lens or "OD"
    active_job_id = order_flow.od_job_id if lens_side == "OD" else order_flow.oe_job_id
    
    if not active_job_id:
        raise HTTPException(status_code=400, detail="Lente ativa não encontrada para retomar.")
        
    order_flow.state = "RIGHT_LENS_PROCESSING" if lens_side == "OD" else "LEFT_LENS_PROCESSING"
    order_flow.last_activity = datetime.datetime.utcnow()
    db.commit()
    
    start_index = order_flow.last_stopped_index or 0
    _trigger_laser_stream(active_job_id, start_index, background_tasks, db)
    
    log_production_event(db, job_id, "ENGRAVING_RESUMED", f"Gravação da Lente {lens_side} retomada do comando {start_index}.", lens_side)
    
    logs = db.query(ProductionLog).filter(ProductionLog.job_id == job_id).order_by(ProductionLog.timestamp.asc()).all()
    order_flow.logs = logs
    return order_flow


@app.post("/api/orders/{job_id}/flow/restart", response_model=OrderFlowResponse)
def restart_order_flow_engraving(job_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    import datetime
    order_flow = db.query(OrderFlow).filter(OrderFlow.job_id == job_id).first()
    if not order_flow:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
        
    lens_side = "OD"
    if order_flow.state == "LEFT_LENS_PROCESSING" or (order_flow.state in ["PAUSED", "ERROR"] and order_flow.last_stopped_lens == "OE"):
        lens_side = "OE"
        
    active_job_id = order_flow.od_job_id if lens_side == "OD" else order_flow.oe_job_id
    if not active_job_id:
        raise HTTPException(status_code=400, detail="Lente ativa não encontrada para reiniciar.")
        
    # Stop streamer if active
    streamer = active_streamers.pop(active_job_id, None)
    if streamer:
        streamer.stop()
        virtual_laser.finish_job()
        
    order_flow.state = "RIGHT_LENS_PROCESSING" if lens_side == "OD" else "LEFT_LENS_PROCESSING"
    order_flow.last_activity = datetime.datetime.utcnow()
    db.commit()
    
    _trigger_laser_stream(active_job_id, 0, background_tasks, db)
    
    log_production_event(db, job_id, "ENGRAVING_RESTARTED", f"Gravação da Lente {lens_side} reiniciada.", lens_side)
    
    logs = db.query(ProductionLog).filter(ProductionLog.job_id == job_id).order_by(ProductionLog.timestamp.asc()).all()
    order_flow.logs = logs
    return order_flow


@app.post("/api/orders/{job_id}/flow/cancel", response_model=OrderFlowResponse)
def cancel_order_flow(job_id: str, db: Session = Depends(get_db)):
    import datetime
    order_flow = db.query(OrderFlow).filter(OrderFlow.job_id == job_id).first()
    if not order_flow:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
        
    if order_flow.od_job_id:
        streamer = active_streamers.pop(order_flow.od_job_id, None)
        if streamer:
            streamer.stop()
    if order_flow.oe_job_id:
        streamer = active_streamers.pop(order_flow.oe_job_id, None)
        if streamer:
            streamer.stop()
            
    virtual_laser.finish_job()
    
    if order_flow.od_status not in ["COMPLETED", "SKIPPED"]:
        order_flow.od_status = "FAILED"
    if order_flow.oe_status not in ["COMPLETED", "SKIPPED"]:
        order_flow.oe_status = "FAILED"
        
    order_flow.state = "CANCELLED"
    order_flow.end_time = datetime.datetime.utcnow()
    order_flow.last_activity = datetime.datetime.utcnow()
    db.commit()
    
    log_production_event(db, job_id, "ENGRAVING_CANCELLED", "Pedido cancelado manualmente pelo operador.", "NONE")
    
    logs = db.query(ProductionLog).filter(ProductionLog.job_id == job_id).order_by(ProductionLog.timestamp.asc()).all()
    order_flow.logs = logs
    return order_flow


@app.get("/api/production/metrics")
def get_production_metrics(db: Session = Depends(get_db)):
    completed = db.query(OrderFlow).filter(OrderFlow.state == "COMPLETED").all()
    completed_count = len(completed)
    
    cycle_times = []
    for f in completed:
        if f.start_time and f.end_time:
            cycle_times.append((f.end_time - f.start_time).total_seconds())
            
    avg_cycle_time = sum(cycle_times) / len(cycle_times) if cycle_times else 0.0
    
    all_flows = db.query(OrderFlow).all()
    t_pause = sum(f.pause_count for f in all_flows)
    t_skip = sum(f.skip_count for f in all_flows)
    t_error = sum(f.error_count for f in all_flows)
    
    avg_engr_time = 0.0
    completed_engr_times = [f.engraving_time_seconds for f in completed]
    if completed_engr_times:
        avg_engr_time = sum(completed_engr_times) / len(completed_engr_times)
        
    return {
        "completed_orders": completed_count,
        "average_cycle_time": round(avg_cycle_time, 1),
        "average_engraving_time": round(avg_engr_time, 1),
        "total_pause_count": t_pause,
        "total_skip_count": t_skip,
        "total_error_count": t_error
    }


# ----------------- Mock OMA Creator (For Testing) -----------------

@app.post("/api/system/mock-job")
def create_mock_oma_job(db: Session = Depends(get_db)):
    """
    Utility endpoint that programmatically dumps a pair of high-fidelity OMA files
    (Right and Left lens) sharing the same JOB ID directly into WATCH_DIR.
    """
    import random
    job_num = random.randint(10000, 99999)
    
    # Construct a slightly oval shaped trace
    shape_lines = []
    for i in range(360):
        rad = math.radians(i)
        r_mm = 32.0 + 3.0 * math.cos(rad * 2.0)
        r_oma = int(r_mm * 100)
        shape_lines.append(str(r_oma))
        
    trcfmt_r = f"R;360;1.0;1.0;R;{';'.join(shape_lines)}"
    trcfmt_l = f"L;360;1.0;1.0;R;{';'.join(shape_lines)}"
    
    # R Lens file
    filename_r = f"job_{job_num}_R.oma"
    filepath_r = WATCH_DIR / filename_r
    oma_lines_r = [
        f"JOB={job_num}",
        f"EYE=R",
        f"LNAM=Freeform progressive MVP R",
        f"LDG=72.0",
        f"AXIS=45",
        f"ADD=2.00",
        f"PRISM=0.0",
        f"PBASE=0.0",
        f"TRCFMT={trcfmt_r}"
    ]
    with open(filepath_r, "w", encoding="utf-8") as f:
        f.write("\n".join(oma_lines_r))
        
    # L Lens file
    filename_l = f"job_{job_num}_L.oma"
    filepath_l = WATCH_DIR / filename_l
    oma_lines_l = [
        f"JOB={job_num}",
        f"EYE=L",
        f"LNAM=Freeform progressive MVP L",
        f"LDG=72.0",
        f"AXIS=135",
        f"ADD=2.00",
        f"PRISM=0.0",
        f"PBASE=0.0",
        f"TRCFMT={trcfmt_l}"
    ]
    with open(filepath_l, "w", encoding="utf-8") as f:
        f.write("\n".join(oma_lines_l))
        
    log_system_event(db, "INFO", f"Programmatically injected paired mock OMA files for JOB: {job_num}")
    
    # Do NOT process manually to prevent concurrent double-processing with Watchdog Folder Monitor.
    # The watchdog will automatically detect files and create jobs.
    # Return the generated job ID so the frontend can select and track it.
    return {
        "message": "Mock OMA Job Pair created",
        "job_id": str(job_num)
    }


@app.post("/api/system/clear-all")
def clear_all_system_data(db: Session = Depends(get_db)):
    """
    Purges all operational records (Jobs, OrderFlows, ProductionLogs, SystemLogs)
    and removes physical OMA input files and generated previews/Gcode.
    """
    # 1. Stop any active streamers
    for streamer in list(active_streamers.values()):
        try:
            streamer.stop()
        except Exception:
            pass
    active_streamers.clear()
    
    # 2. Reset virtual laser
    virtual_laser.finish_job()
    virtual_laser.reset_alarms()
    
    # 3. Purge database tables
    try:
        db.query(Job).delete()
        db.query(OrderFlow).delete()
        db.query(ProductionLog).delete()
        db.query(SystemLog).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao limpar banco de dados: {e}")
        
    # 4. Remove physical files on disk
    # Monitored directory
    if os.path.exists(WATCH_DIR):
        for filename in os.listdir(WATCH_DIR):
            if filename.lower().endswith(('.oma', '.txt')):
                try:
                    os.remove(WATCH_DIR / filename)
                except Exception:
                    pass
    # Output directory
    if os.path.exists(OUTPUT_DIR):
        for filename in os.listdir(OUTPUT_DIR):
            if filename.lower().endswith(('.svg', '.gcode', '.lbrn2')):
                try:
                    os.remove(OUTPUT_DIR / filename)
                except Exception:
                    pass
                    
    log_system_event(db, "INFO", "Sistema completamente reiniciado pelo operador. Todos os dados foram apagados.")
    return {"message": "Sistema reiniciado com sucesso. Todos os dados foram apagados."}


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

