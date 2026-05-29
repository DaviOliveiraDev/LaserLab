import threading
import time
from typing import Optional, Dict, Any

class VirtualLaserMachine:
    """
    Simulates a high-fidelity industrial laser engraving system (SCADA/PLC).
    Tracks active operational states, hardware telemetry sensors (temp, power),
    safety door locking systems, and virtual hardware alarm injections.
    Uses thread-safe locking to prevent concurrent read/write race conditions.
    """
    def __init__(self):
        self._lock = threading.Lock()
        
        # General Machine Telemetry
        self.status = "READY"  # READY, PROCESSING, ERROR, OFFLINE
        self.temperature = 22.5  # Ambient base temperature (°C)
        self.laser_power_w = 0.0  # Standby power (W)
        self.safety_door_locked = True
        
        # Alarm Injection Flags
        self.door_open_alarm = False
        self.overtemp_alarm = False
        self.power_drop_alarm = False
        
        # Streaming Telemetry
        self.current_job_id: Optional[int] = None
        self.current_gcode_line: Optional[str] = None
        self.current_gcode_index = 0
        self.total_gcode_lines = 0
        self.progress_pct = 0.0
        
        # Keep track of when telemetry was last updated
        self.last_update_time = time.time()

    def update_telemetry(self):
        """
        Dynamically adjusts telemetry sensors (temperature, wattage, locks)
        based on active operations and alarm states using simple time-decay physics.
        Should be called before retrieving status or inside operational loops.
        """
        with self._lock:
            now = time.time()
            dt = max(0.1, min(2.0, now - self.last_update_time))
            self.last_update_time = now
            
            # --- Alarm states override ---
            if self.door_open_alarm:
                self.safety_door_locked = False
                self.status = "ERROR"
            else:
                self.safety_door_locked = True
                
            if self.overtemp_alarm:
                self.status = "ERROR"
                # Overtemp shoots up to ~68.4°C
                target_temp = 68.4
                self.temperature += (target_temp - self.temperature) * (0.3 * dt)
            elif self.status == "PROCESSING":
                # Active processing raises temp towards 42.0°C
                target_temp = 42.0
                self.temperature += (target_temp - self.temperature) * (0.1 * dt)
            else:
                # Standby / Idle cools down towards ambient room temperature (22.5°C)
                target_temp = 22.5
                self.temperature += (target_temp - self.temperature) * (0.05 * dt)
                
            # --- Laser Wattage physics ---
            if self.status == "PROCESSING" and not self.overtemp_alarm and not self.door_open_alarm:
                if self.power_drop_alarm:
                    # Simulated laser tube degradation drops output
                    self.laser_power_w = 4.2
                else:
                    self.laser_power_w = 25.0
            else:
                self.laser_power_w = 0.0

    def set_alarm(self, name: str, value: bool):
        """Injects or clears a simulated PLC sensor hardware fault."""
        with self._lock:
            if name == "door_open":
                self.door_open_alarm = value
                if value:
                    self.safety_door_locked = False
                    self.status = "ERROR"
            elif name == "overtemp":
                self.overtemp_alarm = value
                if value:
                    self.status = "ERROR"
            elif name == "power_drop":
                self.power_drop_alarm = value
                if value:
                    # Trigger alert warning but keep status if active
                    if self.status != "PROCESSING":
                        self.status = "ERROR"
            
            # Re-evaluate general state
            if not self.door_open_alarm and not self.overtemp_alarm and not self.power_drop_alarm:
                if self.status == "ERROR":
                    self.status = "READY"
                    
        self.update_telemetry()

    def reset_alarms(self):
        """Clears all hardware faults and restores system to READY."""
        with self._lock:
            self.door_open_alarm = False
            self.overtemp_alarm = False
            self.power_drop_alarm = False
            self.safety_door_locked = True
            self.status = "READY"
            
            # Instantly cool down a bit for user feedback
            if self.temperature > 50.0:
                self.temperature = 42.0
                
        self.update_telemetry()

    def start_job(self, job_id: int, total_lines: int):
        """Locks the simulator into PROCESSING mode."""
        self.update_telemetry()
        with self._lock:
            if self.status == "ERROR":
                raise ValueError("Cannot start job: Hardware simulator is in ERROR state.")
            
            self.status = "PROCESSING"
            self.current_job_id = job_id
            self.total_gcode_lines = total_lines
            self.current_gcode_index = 0
            self.current_gcode_line = "Initializing..."
            self.progress_pct = 0.0

    def update_progress(self, index: int, line: str):
        """Updates line index and active coordinate progress."""
        self.update_telemetry()
        with self._lock:
            # Check for sudden errors during processing
            if self.door_open_alarm or self.overtemp_alarm:
                self.status = "ERROR"
                raise RuntimeError("Hardware interrupt: safety fault triggered mid-cut.")
                
            self.current_gcode_index = index
            self.current_gcode_line = line
            if self.total_gcode_lines > 0:
                self.progress_pct = round((index / self.total_gcode_lines) * 100.0, 1)

    def finish_job(self):
        """Successfully completes the active job and returns to READY."""
        self.update_telemetry()
        with self._lock:
            if self.status == "PROCESSING":
                self.status = "READY"
            self.current_job_id = None
            self.current_gcode_line = None
            self.current_gcode_index = 0
            self.progress_pct = 100.0

    def get_status_dict(self) -> Dict[str, Any]:
        """Returns serializable state for API endpoints."""
        self.update_telemetry()
        with self._lock:
            return {
                "status": self.status,
                "temperature": round(self.temperature, 2),
                "laser_power_w": round(self.laser_power_w, 2),
                "safety_door_locked": self.safety_door_locked,
                "door_open_alarm": self.door_open_alarm,
                "overtemp_alarm": self.overtemp_alarm,
                "power_drop_alarm": self.power_drop_alarm,
                "current_job_id": self.current_job_id,
                "current_gcode_line": self.current_gcode_line,
                "current_gcode_index": self.current_gcode_index,
                "total_gcode_lines": self.total_gcode_lines,
                "progress_pct": self.progress_pct
            }

# Global thread-safe simulator singleton
virtual_laser = VirtualLaserMachine()
