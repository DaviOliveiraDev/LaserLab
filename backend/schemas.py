from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class CalibrationBase(BaseModel):
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0

class CalibrationCreate(CalibrationBase):
    pass

class CalibrationResponse(CalibrationBase):
    id: int
    updated_at: datetime

    class Config:
        from_attributes = True

class JobBase(BaseModel):
    job_id: Optional[str] = None
    filename: str
    eye: Optional[str] = None
    lens_name: Optional[str] = None
    axis: Optional[float] = None
    addition: Optional[float] = None
    diameter: Optional[float] = None
    status: str

class JobResponse(JobBase):
    id: int
    prism: Optional[float] = None
    prism_base: Optional[float] = None
    oma_data: Optional[str] = None
    geometry_json: Optional[Dict[str, Any]] = None
    svg_path: Optional[str] = None
    gcode_path: Optional[str] = None
    lbrn2_path: Optional[str] = None
    error_message: Optional[str] = None
    template_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SystemLogResponse(BaseModel):
    id: int
    level: str
    message: str
    timestamp: datetime

    class Config:
        from_attributes = True

class SystemStatusResponse(BaseModel):
    monitoring: bool
    laser_connected: bool
    laser_port: str
    job_queue_count: int
    calibration: CalibrationBase

class LensTemplateBase(BaseModel):
    name: str
    manufacturer: str
    lens_type: str
    offset_x: float = 0.0
    offset_y: float = 0.0
    rotation: float = 0.0
    fitting_cross_dist: float = 4.0
    reference_point: str = "PRP"
    technical_notes: Optional[str] = None
    is_active: int = 1

class LensTemplateCreate(LensTemplateBase):
    pass

class LensTemplateResponse(LensTemplateBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TemplateHistoryResponse(BaseModel):
    id: int
    template_id: int
    template_name: str
    action: str
    changed_fields: Optional[Dict[str, Any]] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class VirtualMachineStatusResponse(BaseModel):
    status: str
    temperature: float
    laser_power_w: float
    safety_door_locked: bool
    door_open_alarm: bool
    overtemp_alarm: bool
    power_drop_alarm: bool
    current_job_id: Optional[int] = None
    current_gcode_line: Optional[str] = None
    current_gcode_index: int = 0
    total_gcode_lines: int = 0
    progress_pct: float = 0.0


class SimulatorAlarmRequest(BaseModel):
    alarm_name: str
    value: bool

