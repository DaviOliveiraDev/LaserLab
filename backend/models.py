import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON
from backend.database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, index=True, nullable=True)  # From JOB tag in OMA
    filename = Column(String, unique=True, index=True)
    eye = Column(String, nullable=True)                 # R/L or OD/OS
    lens_name = Column(String, nullable=True)           # LNAM
    axis = Column(Float, nullable=True)                 # AXIS
    addition = Column(Float, nullable=True)             # ADD
    prism = Column(Float, nullable=True)
    prism_base = Column(Float, nullable=True)
    diameter = Column(Float, nullable=True)             # LDG
    
    status = Column(String, default="Pending")          # Pending, Parsing, Calculating, Ready, Processing, Success, Failed
    oma_data = Column(Text, nullable=True)              # Raw OMA file text
    parsed_json = Column(JSON, nullable=True)           # Full dictionary of parsed tags
    geometry_json = Column(JSON, nullable=True)         # Outlines, marking coordinates, bounding box
    
    svg_path = Column(String, nullable=True)
    gcode_path = Column(String, nullable=True)
    lbrn2_path = Column(String, nullable=True)
    
    error_message = Column(Text, nullable=True)
    template_id = Column(Integer, nullable=True)        # Applied Lens Template ID
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Calibration(Base):
    __tablename__ = "calibration"

    id = Column(Integer, primary_key=True, index=True)
    offset_x = Column(Float, default=0.0)
    offset_y = Column(Float, default=0.0)
    scale_x = Column(Float, default=1.0)
    scale_y = Column(Float, default=1.0)
    rotation = Column(Float, default=0.0)               # Rotation angle in degrees
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String, default="INFO")              # INFO, WARNING, ERROR, SUCCESS
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class LensTemplate(Base):
    __tablename__ = "lens_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, unique=True)      # e.g., "Zeiss Progressivo HD" (matches OMA LNAM)
    manufacturer = Column(String, index=True)           # e.g., "Zeiss", "Essilor", "Hoya"
    lens_type = Column(String, index=True)              # e.g., "Progressive", "Single Vision", "Office"
    
    offset_x = Column(Float, default=0.0)               # Horizontal engraving offset shift (mm)
    offset_y = Column(Float, default=0.0)               # Vertical engraving offset shift (mm)
    rotation = Column(Float, default=0.0)               # Fine rotation offset for this model (deg)
    fitting_cross_dist = Column(Float, default=4.0)     # Fitting cross vertical height above prism ref point (mm)
    reference_point = Column(String, default="PRP")     # PRP, DRP, MRP, GEOMETRIC_CENTER
    
    technical_notes = Column(Text, nullable=True)
    is_active = Column(Integer, default=1)              # 1 for Active, 0 for Inactive
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class TemplateHistory(Base):
    __tablename__ = "template_history"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, index=True)           # FK equivalent (linked template ID)
    template_name = Column(String)                      # Cached template name for history reference
    action = Column(String)                             # CREATE, UPDATE, DUPLICATE, ACTIVATE, DEACTIVATE
    changed_fields = Column(JSON, nullable=True)        # Dictionary of diff changes (e.g. {"offset_x": [old, new]})
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class OrderFlow(Base):
    __tablename__ = "order_flows"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True, nullable=False)
    state = Column(String, default="WAITING_RIGHT_LENS") # WAITING_RIGHT_LENS, etc.
    current_lens = Column(String, nullable=True)         # OD or OE
    od_job_id = Column(Integer, nullable=True)
    oe_job_id = Column(Integer, nullable=True)
    od_status = Column(String, default="PENDING")        # PENDING, PROCESSING, COMPLETED, SKIPPED, FAILED
    oe_status = Column(String, default="PENDING")        # PENDING, PROCESSING, COMPLETED, SKIPPED, FAILED
    operator_name = Column(String, default="Operador Padrão")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, default=datetime.datetime.utcnow)
    pause_count = Column(Integer, default=0)
    skip_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    engraving_time_seconds = Column(Float, default=0.0)
    last_stopped_lens = Column(String, nullable=True)
    last_stopped_index = Column(Integer, nullable=True)

class ProductionLog(Base):
    __tablename__ = "production_logs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, index=True, nullable=False)
    lens_side = Column(String, nullable=True)            # OD, OE, or NONE
    event_type = Column(String, nullable=False)          # LENS_POSITIONED, etc.
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
