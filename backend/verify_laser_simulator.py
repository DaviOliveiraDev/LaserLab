import sys
import time
import threading
from pathlib import Path

# Add project root directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.laser.simulator import virtual_laser
from backend.laser.laser_integration import GRBLSerialStreamer

def run_simulator_tests():
    print("=" * 60)
    print("   LASER SIMULATOR INTEGRATION & SAFETY INTERRUPT TESTS")
    print("=" * 60)

    # Test 1: Baseline READY state and telemetry decay physics
    print("\n[Test 1] Validating standby telemetry values...")
    virtual_laser.reset_alarms()
    status = virtual_laser.get_status_dict()
    
    print(f"-> State: {status['status']} (Expected: READY)")
    print(f"-> Temperature: {status['temperature']}°C (Expected: ~22.5°C)")
    print(f"-> Wattage: {status['laser_power_w']}W (Expected: 0.0W)")
    print(f"-> Safety Door: {'LOCKED' if status['safety_door_locked'] else 'OPEN'} (Expected: LOCKED)")
    
    assert status['status'] == "READY"
    assert status['safety_door_locked'] is True
    assert status['laser_power_w'] == 0.0
    print("[OK] Standby telemetry verified.")

    # Test 2: Simulating job start and active state
    print("\n[Test 2] Starting mock job and checking active telemetry...")
    dummy_gcode = "G21\nG90\nM3 S200\nG1 X10.0 Y10.0 F1500\nM5\nG0 X0 Y0"
    gcode_lines = [l.strip() for l in dummy_gcode.splitlines() if l.strip() and not l.startswith(";")]
    total_lines = len(gcode_lines)
    
    virtual_laser.start_job(999, total_lines)
    status_act = virtual_laser.get_status_dict()
    print(f"-> State: {status_act['status']} (Expected: PROCESSING)")
    print(f"-> Job ID: {status_act['current_job_id']} (Expected: 999)")
    
    assert status_act['status'] == "PROCESSING"
    assert status_act['current_job_id'] == 999
    
    # Simulate processing first line
    virtual_laser.update_progress(1, gcode_lines[0])
    status_prog = virtual_laser.get_status_dict()
    print(f"-> Line 1: '{status_prog['current_gcode_line']}' (Progress: {status_prog['progress_pct']}%)")
    
    # Check that temperature starts to rise under load
    time.sleep(0.2)
    virtual_laser.update_telemetry()
    status_hot = virtual_laser.get_status_dict()
    print(f"-> Active Temperature: {status_hot['temperature']}°C (Expected: >22.5°C)")
    print(f"-> Active Power: {status_hot['laser_power_w']}W (Expected: 25.0W)")
    
    assert status_hot['temperature'] > 22.5
    assert status_hot['laser_power_w'] == 25.0
    print("[OK] Active state and power usage verified.")

    # Test 3: Emergency Stop - Safety Door Open Alarm Injection
    print("\n[Test 3] Injecting Safety Door Open alarm mid-cut...")
    
    # Trigger alarm
    virtual_laser.set_alarm("door_open", True)
    status_alarm = virtual_laser.get_status_dict()
    print(f"-> State: {status_alarm['status']} (Expected: ERROR)")
    print(f"-> Safety Door: {'LOCKED' if status_alarm['safety_door_locked'] else 'OPEN'} (Expected: OPEN)")
    print(f"-> Laser Wattage: {status_alarm['laser_power_w']}W (Expected: 0.0W for NR-12 compliance)")
    
    assert status_alarm['status'] == "ERROR"
    assert status_alarm['safety_door_locked'] is False
    assert status_alarm['laser_power_w'] == 0.0
    
    # Assert that trying to update progress raises error
    try:
        virtual_laser.update_progress(2, gcode_lines[1])
        print("x ERROR: Progress update allowed during hardware fault!")
        sys.exit(1)
    except RuntimeError as ex:
        print(f"[OK] Blocked update: RuntimeError successfully raised: {ex}")

    # Test 4: Alarm Resetting
    print("\n[Test 4] Resetting safety alarms...")
    virtual_laser.reset_alarms()
    status_reset = virtual_laser.get_status_dict()
    print(f"-> State: {status_reset['status']} (Expected: READY)")
    print(f"-> Safety Door: {'LOCKED' if status_reset['safety_door_locked'] else 'OPEN'} (Expected: LOCKED)")
    
    assert status_reset['status'] == "READY"
    assert status_reset['safety_door_locked'] is True
    print("[OK] Alarms reset verified.")

    # Test 5: Live Streaming Interrupt verification
    print("\n[Test 5] Simulating full GRBL stream with mid-cut door alarm interrupt...")
    streamer = GRBLSerialStreamer(port="COM_MOCK")
    
    # Run the streaming thread
    def run_stream():
        def line_cb(idx, line_content):
            try:
                virtual_laser.update_progress(idx + 1, line_content)
                return True
            except Exception:
                return False
        
        success = streamer.stream_gcode(dummy_gcode, line_callback=line_cb)
        print(f"-> Streamer Finished. Result success: {success} (Expected: False due to door open)")
        assert success is False

    virtual_laser.start_job(999, total_lines)
    
    t = threading.Thread(target=run_stream)
    t.start()
    
    # Wait for line 2 and open the safety door
    time.sleep(0.12)
    print("-> Operator opens door mid-stream!")
    virtual_laser.set_alarm("door_open", True)
    t.join()
    
    status_end = virtual_laser.get_status_dict()
    print(f"-> Final State: {status_end['status']} (Expected: ERROR)")
    assert status_end['status'] == "ERROR"
    
    # Clear alarms
    virtual_laser.reset_alarms()
    print("[OK] Full streamer interrupt scenario passed successfully.")

    print("\n" + "=" * 60)
    print("   SIMULATOR STATUS: ALL HARDWARE INTERRUPT SCENARIOS PASS!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = run_simulator_tests()
    sys.exit(0 if success else 1)
